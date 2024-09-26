@echo off
echo Please enter the full OpenAI API key:
set /p API_KEY= 

setx OPENAI_API_KEY "%API_KEY%"

echo The OPENAI_API_KEY has been set.
pause
