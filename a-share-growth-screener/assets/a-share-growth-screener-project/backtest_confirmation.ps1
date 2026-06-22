param(
  [string]$Period = "20260331",
  [string]$Statuses = "A_confirmed,B_watch"
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
& ".\.venv\Scripts\python.exe" -m stock_screener.confirmation_backtest --period $Period --statuses $Statuses
