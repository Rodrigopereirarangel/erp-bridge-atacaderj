@echo off
cd /d "%~dp0"
if not exist saida mkdir saida
python src\gerar.py %* >> saida\gerar.log 2>&1
if errorlevel 1 echo ERRO - veja saida\gerar.log & exit /b 1
echo OK - abra saida\listagem-fornecedores.html
