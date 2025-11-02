@echo off
REM Script otimizado para marcar artigos como internal
REM Configure as variáveis de ambiente abaixo antes de executar

REM ============================================
REM CONFIGURAÇÃO - EDITE ESTAS LINHAS
REM ============================================

REM Token da API Zammad (obrigatório)
set ZAMMAD_TOKEN=1qbRbHElT2yBzhPPc7sFnE-BQITXT9asONjyx_rH6DyJc-U5JJ7CYWcfWmVa6s2x
set ZAMMAD_BASE_URL=https://ufevsuporte.zammad.com

REM Verificar SSL (opcional: true ou false)
set ZAMMAD_VERIFY_SSL=false

REM ============================================
REM NÃO EDITE ABAIXO DESTA LINHA
REM ============================================

echo ========================================
echo  Zammad - Marcar Artigos (VERSAO RAPIDA)
echo ========================================
echo.
echo Esta versao otimizada:
echo - Processa APENAS tickets abertos
echo - USA CACHE para evitar reprocessar artigos
echo - E muito mais RAPIDA para execucao periodica
echo.
echo ATENCAO: Esta operacao fara alteracoes reais!
echo.
pause

cd /d "%~dp0"
python scripts\mark_articles_internal_fast.py
pause
