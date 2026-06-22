param(
  [string]$Period = "20260630",
  [int]$Limit = 0
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
if ($Limit -gt 0) {
  & ".\.venv\Scripts\python.exe" -m stock_screener.analyze_reports --period $Period --limit $Limit
} else {
  & ".\.venv\Scripts\python.exe" -m stock_screener.analyze_reports --period $Period
}
