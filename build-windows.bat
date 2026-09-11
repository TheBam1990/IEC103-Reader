@echo off
setlocal
py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-build.txt
python -m unittest discover -s tests -v
pyinstaller --clean --noconfirm IEC103-Reader.spec
echo.
echo Fertig: dist\IEC103-Reader.exe
pause
