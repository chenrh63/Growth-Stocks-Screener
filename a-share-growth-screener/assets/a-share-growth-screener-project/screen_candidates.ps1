param(
  [string]$Period = "20260630",
  [int]$TargetCount = 80
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
& ".\.venv\Scripts\python.exe" -m stock_screener.screen_market --period $Period --target-count $TargetCount
