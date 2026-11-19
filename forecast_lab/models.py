"""Adapters for the foundation-model contestants. Each one is optional: if its package or weights are missing,
it raises ContestantUnavailable and the contest runs without it (and says so in the report).

Every adapter feeds the model closes up to and including `asof` only, and returns log-return quantiles at
LEVELS for steps 1..horizon, the shape in core.Forecast.

Status on 2026-11-19: the Kronos adapter reuses the pinned, tested code in kronos/. The TimesFM, Chronos and
Moirai adapters follow each project's documented call and have NOT been run yet; phase 1 on Ashton's PC is
their first run (see docs/forecast-lab.md).
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import zlib
from pathlib import Path

import numpy as np

from .core import HORIZON, LEVELS, ContestantUnavailable, closes, from_samples, next_trading_days

ROOT = Path(__file__).resolve().parent.parent
CONTEXT = 512  # past daily closes fed to every model (Kronos-small's limit; the others allow more)


def _price_q_to_logret(price_q: np.ndarray, last: float) -> np.ndarray:
    p = np.maximum(np.asarray(price_q, float), 1e-9)
    return np.log(p / last)


def _need(module: str, pip_hint: str):
    import importlib
    try:
        return importlib.import_module(module)
    except Exception as e:  # ImportError or a broken install
        raise ContestantUnavailable(f"{module} is not installed ({pip_hint})") from e


# ---------------------------------------------------------------- Kronos-small (pinned, already in the repo)

def fetch_kronos_weights(dest: Path) -> Path:
    """Download the pinned Kronos weights once, check every sha256 against kronos/MANIFEST.json, keep safetensors only."""
    man = json.loads((ROOT / "kronos" / "MANIFEST.json").read_text(encoding="utf-8"))
    dest = Path(dest)
    for part, pin in man["weights"].items():
        d = dest / part
        d.mkdir(parents=True, exist_ok=True)
        for name, digest in pin["sha256"].items():
            if name not in ("config.json", "model.safetensors") or len(pin["revision"]) != 40:
                raise ContestantUnavailable("unexpected file in the Kronos pin")
            f = d / name
            if f.exists() and hashlib.sha256(f.read_bytes()).hexdigest() == digest:
                continue
            url = f"https://huggingface.co/{pin['repo']}/resolve/{pin['revision']}/{name}"
            req = urllib.request.Request(url, headers={"User-Agent": "forecast-lab/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read(200_000_000)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ContestantUnavailable(f"{part}/{name}: sha256 does not match the pin")
            f.write_bytes(data)
    return dest


class Kronos:
    name = "kronos_small"
    paths = 100

    def __init__(self, weights_dir: str | os.PathLike | None = None):
        self.weights_dir = Path(weights_dir or os.environ.get("FORECAST_LAB_KRONOS_WEIGHTS", ROOT / ".weights" / "kronos"))
        self._models = None

    def _load(self):
        if self._models is None:
            _need("torch", "pip install -r kronos/requirements.txt")
            import sys
            sys.path.insert(0, str(ROOT / "kronos"))
            import kronos_paths as kp  # noqa: E402  (pinned loader: sha256 check, safetensors only)
            if not (self.weights_dir / "model" / "model.safetensors").exists():
                raise ContestantUnavailable(f"Kronos weights not found in {self.weights_dir} (python -m forecast_lab weights)")
            self._kp = kp
            self._models = kp.load_models(self.weights_dir)
        return self._models

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        tok, mod = self._load()
        d = df[["open", "high", "low", "close", "volume"]].astype(float).dropna().iloc[-CONTEXT:]
        last = float(d["close"].iloc[-1])
        y_dates = next_trading_days(d.index[-1], horizon)
        s = json.loads((ROOT / "kronos" / "MANIFEST.json").read_text(encoding="utf-8"))["sampling"]
        seed = zlib.crc32(f"{ticker}|{asof}".encode()) & 0x7FFFFFFF
        p = self._kp.sample_paths(tok, mod, [{"ohlcv": d.to_numpy(), "x_dates": list(d.index), "y_dates": y_dates}],
                                  horizon, self.paths, T=s["T"], top_k=s["top_k"], top_p=s["top_p"], seed=seed,
                                  max_context=s["max_context"], clip=s["clip"])[0]
        return from_samples(np.log(np.maximum(p[:, :, 3], 1e-9) / last))


# ---------------------------------------------------------------- TimesFM 2.5 (Google, Apache-2.0 code and weights)

class TimesFM:
    name = "timesfm_2_5"
    repo = "google/timesfm-2.5-200m-pytorch"

    def __init__(self):
        self._m = None

    def _load(self):
        if self._m is None:
            tf = _need("timesfm", "clone google-research/timesfm, then pip install -e .[torch]")
            m = tf.TimesFM_2p5_200M_torch.from_pretrained(self.repo, torch_compile=False)
            m.compile(tf.ForecastConfig(max_context=CONTEXT, max_horizon=64, normalize_inputs=True,
                                        use_continuous_quantile_head=True, force_flip_invariance=True,
                                        infer_is_positive=True, fix_quantile_crossing=True))
            self._m = m
        return self._m

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        c = closes(df).to_numpy()[-CONTEXT:]
        _, q = self._load().forecast(horizon=horizon, inputs=[c])
        q = np.asarray(q)[0, :horizon, 1:10]  # column 0 is the mean, then p10..p90
        return _price_q_to_logret(q, float(c[-1]))


# ---------------------------------------------------------------- Chronos-Bolt small (Amazon, Apache-2.0)

class Chronos:
    name = "chronos_bolt_small"
    repo = "amazon/chronos-bolt-small"

    def __init__(self):
        self._p = None

    def _load(self):
        if self._p is None:
            ch = _need("chronos", "pip install chronos-forecasting")
            self._p = ch.BaseChronosPipeline.from_pretrained(self.repo, device_map="cpu")
        return self._p

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        torch = _need("torch", "pip install chronos-forecasting")
        c = closes(df).to_numpy()[-CONTEXT:]
        out = self._load().predict(torch.tensor(c, dtype=torch.float32), prediction_length=horizon)
        q = np.asarray(out)[0].T  # [quantiles, horizon] -> [horizon, quantiles]; Bolt's levels are 0.1..0.9
        if q.shape[1] != len(LEVELS):
            raise ContestantUnavailable("Chronos-Bolt returned unexpected quantile levels")
        return _price_q_to_logret(q, float(c[-1]))


# ---------------------------------------------------------------- Moirai 2 small (Salesforce; weights CC-BY-NC 4.0, personal use only)

class Moirai:
    name = "moirai_2_small"
    repo = "Salesforce/moirai-2.0-R-small"

    def __init__(self):
        self._pred = None

    def _load(self, horizon: int):
        if self._pred is None:
            m2 = _need("uni2ts.model.moirai2", "clone SalesforceAIResearch/uni2ts, then pip install -e .")
            model = m2.Moirai2Forecast(module=m2.Moirai2Module.from_pretrained(self.repo), prediction_length=horizon,
                                       context_length=CONTEXT, target_dim=1, feat_dynamic_real_dim=0,
                                       past_feat_dynamic_real_dim=0)
            self._pred = model.create_predictor(batch_size=1)
        return self._pred

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        gl = _need("gluonts.dataset.common", "installed with uni2ts")
        import pandas as pd
        s = closes(df).iloc[-CONTEXT:]
        ds = gl.ListDataset([{"start": pd.Period(s.index[0], freq="B"), "target": s.to_numpy()}], freq="B")
        fc = next(iter(self._load(horizon).predict(ds)))
        q = np.stack([np.asarray(fc.quantile(lv))[:horizon] for lv in LEVELS], axis=1)
        return _price_q_to_logret(q, float(s.iloc[-1]))


MODELS = {c.name: c for c in (Kronos, TimesFM, Chronos, Moirai)}
