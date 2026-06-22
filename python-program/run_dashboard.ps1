$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
& ".\.venv\Scripts\python.exe" -m streamlit run app.py

