@echo off
REM Script de debug para verificar por que o fast não está funcionando

REM ============================================
REM CONFIGURAÇÃO - EDITE ESTAS LINHAS
REM ============================================

REM Token da API Zammad (obrigatório)
set ZAMMAD_TOKEN=1qbRbHElT2yBzhPPc7sFnE-BQITXT9asONjyx_rH6DyJc-U5JJ7CYWcfWmVa6s2x
set ZAMMAD_BASE_URL=https://ufevsuporte.zammad.com

REM Verificar SSL (opcional: true ou false)
set ZAMMAD_VERIFY_SSL=false

REM ============================================
REM DEBUG
REM ============================================

echo ========================================
echo  DEBUG - Verificar Fast Script
echo ========================================
echo.
echo Este script vai fazer debug para verificar
echo por que o script fast nao esta retornando artigos.
echo.
pause

cd /d "%~dp0"
python scripts\debug_fast.py
pause
