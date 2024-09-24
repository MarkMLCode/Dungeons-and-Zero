py -3.10 -m venv venv
call .\venv\Scripts\activate.bat

python -m pip install --upgrade pip 
python -m pip install -r src/ai/requirements.txt

pause
deactivate
