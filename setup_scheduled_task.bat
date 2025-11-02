@echo off
REM Script para configurar execução automática no Windows Task Scheduler

echo ========================================
echo  Configurar Execucao Automatica
echo ========================================
echo.
echo Este script vai configurar uma tarefa no Windows
echo para executar automaticamente a marcacao de artigos
echo a cada X horas/minutos.
echo.

REM Obter o diretório atual
set SCRIPT_DIR=%~dp0
set SCRIPT_PATH=%SCRIPT_DIR%run_mark_articles_fast.bat

echo Diretorio do script: %SCRIPT_DIR%
echo Caminho completo: %SCRIPT_PATH%
echo.

echo Escolha a frequencia de execucao:
echo 1) A cada 30 minutos
echo 2) A cada 1 hora  
echo 3) A cada 2 horas
echo 4) A cada 4 horas
echo 5) A cada 6 horas
echo 6) Personalizado
echo.
set /p choice="Digite sua opcao (1-6): "

if "%choice%"=="1" (
    set INTERVAL=30
    set UNIT=MINUTE
    set TASK_NAME=ZammadMarkArticles_30min
)
if "%choice%"=="2" (
    set INTERVAL=1
    set UNIT=HOURLY
    set TASK_NAME=ZammadMarkArticles_1h
)
if "%choice%"=="3" (
    set INTERVAL=2
    set UNIT=HOURLY
    set TASK_NAME=ZammadMarkArticles_2h
)
if "%choice%"=="4" (
    set INTERVAL=4
    set UNIT=HOURLY
    set TASK_NAME=ZammadMarkArticles_4h
)
if "%choice%"=="5" (
    set INTERVAL=6
    set UNIT=HOURLY
    set TASK_NAME=ZammadMarkArticles_6h
)
if "%choice%"=="6" (
    set /p INTERVAL="Digite o intervalo em minutos: "
    set UNIT=MINUTE
    set TASK_NAME=ZammadMarkArticles_custom
)

echo.
echo Configurando tarefa: %TASK_NAME%
echo Intervalo: %INTERVAL% %UNIT%
echo Script: %SCRIPT_PATH%
echo.

REM Criar a tarefa agendada
if "%UNIT%"=="MINUTE" (
    schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc minute /mo %INTERVAL% /f
) else (
    schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc hourly /mo %INTERVAL% /f
)

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✓ Tarefa criada com sucesso!
    echo.
    echo Para gerenciar a tarefa:
    echo - Abrir Task Scheduler: taskschd.msc
    echo - Ou usar comandos:
    echo   schtasks /query /tn "%TASK_NAME%"     (ver status)
    echo   schtasks /run /tn "%TASK_NAME%"       (executar agora)
    echo   schtasks /end /tn "%TASK_NAME%"       (parar execucao)
    echo   schtasks /delete /tn "%TASK_NAME%"    (remover tarefa)
    echo.
    
    set /p run_now="Executar a tarefa agora para testar? (s/n): "
    if /i "%run_now%"=="s" (
        echo Executando tarefa...
        schtasks /run /tn "%TASK_NAME%"
    )
) else (
    echo.
    echo ✗ Erro ao criar a tarefa!
    echo Verifique se esta executando como Administrador.
)

echo.
pause
