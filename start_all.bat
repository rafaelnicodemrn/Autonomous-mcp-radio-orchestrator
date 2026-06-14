@echo off
echo Iniciando RadioIA Pessoal...
echo.

start "RadioIA Player" cmd /k "cd /d C:\radio\radioIA && .venv\Scripts\activate && python serve.py"
timeout /t 3 /nobreak > nul

start "RadioIA Scheduler" cmd /k "cd /d C:\radio\radioIA && .venv\Scripts\activate && python scheduler.py"
timeout /t 2 /nobreak > nul

start "RadioIA Telegram" cmd /k "cd /d C:\radio\radioIA && .venv\Scripts\activate && python telegram_bot.py"

echo.
echo Todos os processos iniciados:
echo   - Player Web:  http://localhost:5000
echo   - Scheduler:   gerando episodios conforme grade
echo   - Telegram Bot: @radiobootbot
echo.
echo Para parar tudo, feche as janelas abertas.
pause
