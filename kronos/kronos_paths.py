"""Run the pinned Kronos-small model on CPU and keep every sampled path (no averaging).

Private paper-trading experiment. Not investment advice.
Third-party model code lives in vendor/kronos (MIT, pinned commit, see MANIFEST.json). This file is ours.
Safety rules, all enforced here:
  - Weights load only from local files whose sha256 matches MANIFEST.json, and only through safetensors
    (safetensors.torch.load_file). No pickle, no torch.load, no Hugging Face download code is imported.
  - config.json may hold only the known keys, each a plain int, float or bool; anything else is refused.
  - block_network() is called before the model runs, so the model step cannot open a socket.
The inference loop mirrors upstream auto_regressive_inference (model/kronos.py) step for step, except that the
sampled paths are returned one by one instead of being averaged.
"""
from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "MANIFEST.json"
PRICE_COLS = ["open", "high", "low", "close", "volume", "amount"]
TOKENIZER_KEYS = {"attn_dropout_p": float, "beta": float, "d_in": int, "d_model": int, "ff_dim": int, "ffn_dropout_p": float,
                  "gamma": float, "gamma0": float, "group_size": int, "n_dec_layers": int, "n_enc_layers": int, "n_heads": int,
                  "resid_dropout_p": float, "s1_bits": int, "s2_bits": int, "zeta": float}
MODEL_KEYS = {"attn_dropout_p": float, "d_model": int, "ff_dim": int, "ffn_dropout_p": float, "learn_te": bool, "n_heads": int,
              "n_layers": int, "resid_dropout_p": float, "s1_bits": int, "s2_bits": int, "token_dropout_p": float}


class KronosError(RuntimeError):
    pass


def block_network() -> None:
    """After this, any attempt to open a network connection in this process raises."""
    def refuse(*a, **k):
        raise KronosError("network is blocked while the Kronos model runs")
    socket.socket.connect = refuse  # type: ignore[assignment]
    socket.socket.connect_ex = refuse  # type: ignore[assignment]
    socket.create_connection = refuse  # type: ignore[assignment]
    socket.getaddrinfo = refuse  # type: ignore[assignment]


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_config(cfg, keys: dict) -> dict:
    if not isinstance(cfg, dict) or set(cfg) != set(keys):
        raise KronosError("config.json keys do not match the pinned model")
    out = {}
    for k, typ in keys.items():
        v = cfg[k]
        if typ is bool:
            ok = isinstance(v, bool)
        elif typ is int:
            ok = isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100_000
        else:
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= float(v) <= 100
        if not ok:
            raise KronosError(f"config.json value {k} has the wrong type or range")
        out[k] = typ(v) if typ is not bool else v
    return out


def verify_files(weights_dir: Path, man: dict | None = None) -> None:
    """Every pinned file must exist and match its sha256. Any other weight format in the folder is refused."""
    man = man or manifest()
    for part in ("tokenizer", "model"):
        d = Path(weights_dir) / part
        for name, digest in man["weights"][part]["sha256"].items():
            p = d / name
            if not p.is_file() or sha256(p) != digest:
                raise KronosError(f"{part}/{name} is missing or its sha256 does not match the pin")
        extra = [p.name for p in d.iterdir() if p.suffix in {".bin", ".pt", ".pth", ".pkl", ".ckpt"}]
        if extra:
            raise KronosError(f"refusing pickle weight files in {part}: {extra}")


def _vendor():
    import importlib
    import sys
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    return importlib.import_module("vendor.kronos.model")


def load_models(weights_dir: Path, man: dict | None = None):
    import torch
    from safetensors.torch import load_file

    man = man or manifest()
    verify_files(weights_dir, man)
    vk = _vendor()
    wd = Path(weights_dir)
    tcfg = check_config(json.loads((wd / "tokenizer" / "config.json").read_text(encoding="utf-8")), TOKENIZER_KEYS)
    mcfg = check_config(json.loads((wd / "model" / "config.json").read_text(encoding="utf-8")), MODEL_KEYS)
    tok = vk.KronosTokenizer(**tcfg)
    mod = vk.Kronos(**mcfg)
    tok.load_state_dict(load_file(str(wd / "tokenizer" / "model.safetensors"), device="cpu"), strict=True)
    mod.load_state_dict(load_file(str(wd / "model" / "model.safetensors"), device="cpu"), strict=True)
    tok.eval()
    mod.eval()
    torch.set_grad_enabled(False)
    return tok, mod


def time_features(dates) -> np.ndarray:
    """Upstream calc_time_stamps for daily bars: minute, hour, weekday, day, month (minute and hour are 0)."""
    import pandas as pd
    ts = pd.Series(pd.to_datetime(list(dates)))
    return np.stack([ts.dt.minute, ts.dt.hour, ts.dt.weekday, ts.dt.day, ts.dt.month], axis=1).astype(np.float32)


def normalize(ohlcv: np.ndarray, clip: float = 5.0):
    """Upstream KronosPredictor preprocessing: amount = volume x mean(OHLC); z-score per column; clip."""
    x = np.asarray(ohlcv, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] not in (4, 5):
        raise KronosError("input must be rows of open, high, low, close[, volume]")
    if x.shape[1] == 4:
        x = np.concatenate([x, np.zeros((len(x), 2))], axis=1)
    else:
        x = np.concatenate([x, (x[:, 4] * x[:, :4].mean(axis=1))[:, None]], axis=1)
    if not np.isfinite(x).all():
        raise KronosError("input has missing values")
    x = x.astype(np.float32)
    mean, std = x.mean(axis=0), x.std(axis=0)
    z = np.clip((x - mean) / (std + 1e-5), -clip, clip)
    return z, mean, std


def sample_paths(tok, mod, series: list[dict], pred_len: int, n: int, *, T: float = 1.0, top_k: int = 0, top_p: float = 0.9,
                 seed: int = 0, max_context: int = 512, clip: float = 5.0) -> list[np.ndarray]:
    """For each series {"ohlcv": (L, 4 or 5), "x_dates": L dates, "y_dates": pred_len dates} (all the same L), return an
    array (n, pred_len, 6) of sampled open, high, low, close, volume, amount paths in price units."""
    import torch
    vk = _vendor()
    if not series:
        return []
    L = len(series[0]["ohlcv"])
    if any(len(s["ohlcv"]) != L or len(s["x_dates"]) != L or len(s["y_dates"]) != pred_len for s in series):
        raise KronosError("every series in a batch needs the same lookback and horizon")
    torch.manual_seed(seed)
    zs, means, stds, xs, ys = [], [], [], [], []
    for s in series:
        z, m, sd = normalize(s["ohlcv"], clip)
        zs.append(z), means.append(m), stds.append(sd)
        xs.append(time_features(s["x_dates"])), ys.append(time_features(s["y_dates"]))
    x = torch.from_numpy(np.stack(zs))
    x_stamp = torch.from_numpy(np.stack(xs))
    y_stamp = torch.from_numpy(np.stack(ys))
    with torch.no_grad():
        x = torch.clip(x, -clip, clip)
        x = x.unsqueeze(1).repeat(1, n, 1, 1).reshape(-1, x.size(1), x.size(2))
        x_stamp = x_stamp.unsqueeze(1).repeat(1, n, 1, 1).reshape(-1, x_stamp.size(1), x_stamp.size(2))
        y_stamp = y_stamp.unsqueeze(1).repeat(1, n, 1, 1).reshape(-1, y_stamp.size(1), y_stamp.size(2))
        x_token = tok.encode(x, half=True)
        initial = x.size(1)
        batch = x_token[0].size(0)
        total = initial + pred_len
        full_stamp = torch.cat([x_stamp, y_stamp], dim=1)
        gen_pre = x_token[0].new_empty(batch, pred_len)
        gen_post = x_token[1].new_empty(batch, pred_len)
        pre_buf = x_token[0].new_zeros(batch, max_context)
        post_buf = x_token[1].new_zeros(batch, max_context)
        blen = min(initial, max_context)
        if blen > 0:
            st = max(0, initial - max_context)
            pre_buf[:, :blen] = x_token[0][:, st:st + blen]
            post_buf[:, :blen] = x_token[1][:, st:st + blen]
        for i in range(pred_len):
            cur = initial + i
            win = min(cur, max_context)
            inp = [pre_buf[:, :win], post_buf[:, :win]] if cur <= max_context else [pre_buf, post_buf]
            cstart = max(0, cur - max_context)
            stamp = full_stamp[:, cstart:cur, :].contiguous()
            s1_logits, ctx = mod.decode_s1(inp[0], inp[1], stamp)
            s_pre = vk.sample_from_logits(s1_logits[:, -1, :], temperature=T, top_k=top_k, top_p=top_p, sample_logits=True)
            s2_logits = mod.decode_s2(ctx, s_pre)
            s_post = vk.sample_from_logits(s2_logits[:, -1, :], temperature=T, top_k=top_k, top_p=top_p, sample_logits=True)
            gen_pre[:, i] = s_pre.squeeze(-1)
            gen_post[:, i] = s_post.squeeze(-1)
            if cur < max_context:
                pre_buf[:, cur] = s_pre.squeeze(-1)
                post_buf[:, cur] = s_post.squeeze(-1)
            else:
                pre_buf.copy_(torch.roll(pre_buf, shifts=-1, dims=1))
                post_buf.copy_(torch.roll(post_buf, shifts=-1, dims=1))
                pre_buf[:, -1] = s_pre.squeeze(-1)
                post_buf[:, -1] = s_post.squeeze(-1)
        full_pre = torch.cat([x_token[0], gen_pre], dim=1)
        full_post = torch.cat([x_token[1], gen_post], dim=1)
        cstart = max(0, total - max_context)
        z = tok.decode([full_pre[:, cstart:total].contiguous(), full_post[:, cstart:total].contiguous()], half=True)
        z = z.reshape(len(series), n, z.size(1), z.size(2)).cpu().numpy()[:, :, -pred_len:, :]
    return [z[i] * (stds[i] + 1e-5) + means[i] for i in range(len(series))]
