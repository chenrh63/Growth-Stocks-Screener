param(
    [string]$StartPeriod = "20210331",
    [string]$EndPeriod = "20260331",
    [string]$Quarters = "0331",
    [int]$TargetCount = 30,
    [string]$StartDate = "20200101",
    [string]$EndDate = "",
    [string]$OutputTag = ""
)

$ErrorActionPreference = "Stop"
$argsList = @(
    "-m", "stock_screener.historical_backtest",
    "--start-period", $StartPeriod,
    "--end-period", $EndPeriod,
    "--quarters", $Quarters,
    "--target-count", "$TargetCount",
    "--start-date", $StartDate
)
if ($EndDate) { $argsList += @("--end-date", $EndDate) }
if ($OutputTag) { $argsList += @("--output-tag", $OutputTag) }
& ".\.venv\Scripts\python.exe" @argsList
