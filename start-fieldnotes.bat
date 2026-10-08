@echo off
REM Double-click to start Fieldnotes in your browser (no tech skills needed).
REM Requires Ollama running with the model pulled: ollama serve / ollama pull gemma3:1b
cd /d "%~dp0"
.\.venv\Scripts\python.exe app.py
pause
