# Forecast Lab nightly run (Windows Task Scheduler job "ForecastLabNightly").
# Paper money only: nothing here trades, signs in to a brokerage or moves money.
#
# 1. Updates the Forecast Lab branch (never main).
# 2. Runs the tests and the full contest backtest in plain Python (no AI, no cost).
# 3. If Claude Code is installed, runs it headless to fix any contestant that failed.
#    Claude may edit and commit, but cannot push: this script pushes, only to the branch,
#    and only if every changed file is under forecast_lab/, tests/ or docs/.
# Log: logs\forecast_lab\night-YYYY-MM-DD.log (not in git).
param([int]$Weeks = 52, [switch]$NoClaude)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$Branch = "claude/project-thread-yrciat"
$Holdings = Join-Path $HOME "forecast-lab-private\holdings.txt"
Set-Location $Repo

$LogDir = Join-Path $Repo "logs\forecast_lab"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Log = Join-Path $LogDir ("night-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

function Log($m) { ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) | Tee-Object -FilePath $Log -Append | Out-Host }
function Run($exe, [string[]]$a) {
    & $exe @a 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $Log -Append | Out-Host
    return $LASTEXITCODE
}

$vpy = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Log "No .venv found. Run scripts\forecast_lab_setup.ps1 first."; exit 1 }
$env:PATH = (Join-Path $Repo ".venv\Scripts") + ";" + $env:PATH

Log "Forecast Lab night run starting"
$null = Run "git" @("fetch", "origin", $Branch)
$null = Run "git" @("checkout", $Branch)
if ((git rev-parse --abbrev-ref HEAD) -ne $Branch) { Log "Not on $Branch, stopping."; exit 1 }
$null = Run "git" @("pull", "--ff-only", "origin", $Branch)

$tests = Run $vpy @("-m", "pytest", "-q", "tests/test_forecast_lab.py")
Log "Tests exit code: $tests"

$runArgs = @("-m", "forecast_lab", "backtest", "--weeks", "$Weeks", "--refresh")
if (Test-Path $Holdings) { $runArgs += @("--extra-file", $Holdings) }
$bt = Run $vpy $runArgs
Log "Backtest exit code: $bt"

$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($NoClaude -or -not $claude) {
    Log "Skipping Claude Code (not installed or -NoClaude). Night run done."
    exit 0
}

$before = (git rev-parse HEAD)
$prompt = Get-Content (Join-Path $Repo "scripts\forecast_lab_night_prompt.txt") -Raw
$prompt = $prompt + "`n`nTonight's log file: logs/forecast_lab/" + (Split-Path $Log -Leaf) + "`n"
Log "Running Claude Code (headless, Sonnet, max 40 turns)"
$prompt | & claude -p --model sonnet --max-turns 40 --permission-mode acceptEdits `
    --allowedTools "Read" "Edit" "Write" "Glob" "Grep" "Bash(python:*)" "Bash(pip:*)" `
    "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(git add:*)" "Bash(git commit:*)" 2>&1 |
    ForEach-Object { "$_" } | Tee-Object -FilePath $Log -Append | Out-Host
Log "Claude Code exit code: $LASTEXITCODE"

if ((git rev-parse --abbrev-ref HEAD) -ne $Branch) { Log "Claude left the branch; not pushing."; exit 1 }
$after = (git rev-parse HEAD)
if ($after -eq $before) { Log "No new commits. Night run done."; exit 0 }

$bad = git diff --name-only "$before..$after" | Where-Object { $_ -notmatch '^(forecast_lab|tests|docs)/' }
if ($bad) {
    Log "Not pushing: commits touch files outside forecast_lab/, tests/ or docs/: $($bad -join ', ')"
    exit 1
}
$null = Run "git" @("push", "origin", "HEAD:refs/heads/$Branch")
Log "Pushed to $Branch. Night run done."
