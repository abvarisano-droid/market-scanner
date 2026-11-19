# Forecast Lab setup for Windows (PowerShell 5.1 or 7).
# Paper money only: nothing here trades, signs in to a brokerage or moves money.
#
# What it does, in order:
#   1. Puts this folder on the Forecast Lab branch (never main).
#   2. Makes a private Python environment in .venv and installs what the lab needs.
#   3. Downloads the Kronos-small weights (checked against their sha256 pins).
#   4. Runs the tests.
#   5. Runs a quick first contest (8 weeks) and prints the scorecard.
#   6. Adds a nightly Task Scheduler job, "ForecastLabNightly", that runs scripts\forecast_lab_nightly.ps1.
#
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File scripts\forecast_lab_setup.ps1
# Options: -Time "01:30" (nightly start), -SkipFirstRun, -SkipSchedule
param(
    [string]$Time = "01:30",
    [switch]$SkipFirstRun,
    [switch]$SkipSchedule
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$Branch = "claude/project-thread-yrciat"
$Private = Join-Path $HOME "forecast-lab-private"
$Holdings = Join-Path $Private "holdings.txt"
Set-Location $Repo

function Step($msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }
function Stop-If($what) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Stopped: $what failed (exit code $LASTEXITCODE). Copy the red text above and send it to Claude." -ForegroundColor Red
        exit 1
    }
}

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in "3.12", "3.11", "3.10") {
            & py "-$v" -c "print(1)" *> $null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$v") }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($ver -in "3.10", "3.11", "3.12") { return @("python") }
    }
    return $null
}

Step "1/6 Switching to the Forecast Lab branch"
git fetch origin $Branch; Stop-If "git fetch"
git checkout $Branch; Stop-If "git checkout"
git pull --ff-only origin $Branch; Stop-If "git pull"

Step "2/6 Making the Python environment (.venv)"
$vpy = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) {
    $py = Find-Python
    if (-not $py) {
        Write-Host "No Python 3.10 to 3.12 found. Run:  winget install Python.Python.3.12  then close and reopen the terminal and run this again." -ForegroundColor Red
        exit 1
    }
    $exe = $py[0]; $pyArgs = @($py | Select-Object -Skip 1)
    & $exe @pyArgs -m venv .venv; Stop-If "making .venv"
}
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install torch --index-url https://download.pytorch.org/whl/cpu; Stop-If "installing torch"
& $vpy -m pip install -r requirements.txt einops safetensors pytest; Stop-If "installing the lab's packages"
& $vpy -m pip install chronos-forecasting
if ($LASTEXITCODE -ne 0) { Write-Host "Chronos did not install. The lab still runs; the nightly agent will retry it." -ForegroundColor Yellow }

Step "3/6 Downloading the Kronos-small weights"
& $vpy -m forecast_lab weights; Stop-If "downloading the Kronos weights"

Step "4/6 Running the tests"
& $vpy -m pytest -q tests/test_forecast_lab.py; Stop-If "the tests"

if (-not $SkipFirstRun) {
    Step "5/6 Quick first contest: 30 big stocks, last 8 weeks (can take 30 to 60 minutes)"
    $runArgs = @("-m", "forecast_lab", "backtest", "--weeks", "8",
                 "--models", "random_walk,gbm,bootstrap,kronos_small,chronos_bolt_small")
    if (Test-Path $Holdings) { $runArgs += @("--extra-file", $Holdings) }
    & $vpy @runArgs; Stop-If "the first contest"
    $md = Get-ChildItem (Join-Path $Repo "reports\forecast_lab\contest-*.md") -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime | Select-Object -Last 1
    if ($md) {
        Write-Host ""
        Get-Content $md.FullName
        Write-Host ""
        Write-Host "Saved to $($md.FullName) (stays on this PC, not in git)." -ForegroundColor Green
    }
}

if (-not $SkipSchedule) {
    Step "6/6 Adding the nightly job (ForecastLabNightly at $Time)"
    $script = Join-Path $Repo "scripts\forecast_lab_nightly.ps1"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Minimized -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $Repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 7) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName "ForecastLabNightly" -Action $action -Trigger $trigger -Settings $settings `
        -Description "Forecast Lab: nightly paper-money model contest, then Claude Code fixes on the branch. Never trades." -Force | Out-Null
    Write-Host "Nightly job added. Logs go to $Repo\logs\forecast_lab\" -ForegroundColor Green
    Write-Host "Pause it:  Disable-ScheduledTask -TaskName ForecastLabNightly"
    Write-Host "Remove it: Unregister-ScheduledTask -TaskName ForecastLabNightly -Confirm:`$false"
}

Write-Host ""
Write-Host "Done. A model range, not a prediction. Not investment advice." -ForegroundColor Green
