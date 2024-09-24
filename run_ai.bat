call .\venv\Scripts\activate.bat
set PATH=.\bin\;%PATH%
set PYTHONUTF8=1
cd src
python ai_main.py convo
pause