# Versão Rápida - Marcação Automática de Artigos

Esta é a versão **otimizada** do script para execução periódica automática.

## 🚀 Otimizações Implementadas

### 1. **Apenas Tickets Abertos**
- Ignora completamente tickets fechados
- Usa API de search com filtro: `state:new OR state:open OR state:"pending reminder" OR state:"pending close"`
- **Resultado**: 80-90% menos tickets para processar

### 2. **Sistema de Cache Inteligente**
- Salva artigos já processados em `processed_articles_cache.json`
- Evita reprocessar artigos que já foram verificados
- Cache expira automaticamente após 7 dias
- **Resultado**: Execuções subsequentes são 95% mais rápidas

### 3. **Timeouts Otimizados**
- Timeout reduzido para 30s (vs 60s da versão original)
- Melhor para execução frequente

### 4. **Logs Periódicos**
- Salva cache a cada 50 tickets processados
- Evita perda de progresso em caso de interrupção

## 📁 Arquivos da Versão Rápida

| Arquivo | Descrição |
|---------|-----------|
| `mark_articles_internal_fast.py` | Script principal otimizado |
| `run_mark_articles_fast.bat` | Execução manual (com prompts) |
| `run_mark_articles_fast_test.bat` | Teste manual (dry-run) |
| `run_mark_articles_fast_silent.bat` | Execução silenciosa (para automação) |
| `setup_scheduled_task.bat` | Configurar agendamento automático |
| `processed_articles_cache.json` | Cache (criado automaticamente) |

## 🕐 Configuração de Execução Automática

### Opção 1: Configuração Automática
```bash
# Execute como Administrador
setup_scheduled_task.bat
```

Escolha a frequência:
- A cada 30 minutos ⚡ (recomendado para alta atividade)
- A cada 1 hora 🔄 (recomendado para uso normal)  
- A cada 2-6 horas 📅 (para baixa atividade)

### Opção 2: Configuração Manual
```bash
# Criar tarefa para executar a cada hora
schtasks /create /tn "ZammadMarkArticles" /tr "C:\caminho\para\run_mark_articles_fast_silent.bat" /sc hourly /mo 1 /f
```

## 📊 Comparação de Performance

| Aspecto | Versão Original | Versão Rápida |
|---------|----------------|---------------|
| **Tickets processados** | Todos (~1500) | Apenas abertos (~200) |
| **Primeira execução** | ~15-20 min | ~3-5 min |
| **Execuções seguintes** | ~15-20 min | ~30-60 seg |
| **Cache** | ❌ Não | ✅ Sim |
| **Logs automáticos** | ❌ Não | ✅ Sim |
| **Adequado para automação** | ❌ Não | ✅ Sim |

## 🔧 Como Usar

### 1. Primeira Execução (Teste)
```bash
run_mark_articles_fast_test.bat
```

### 2. Primeira Execução (Real)
```bash
run_mark_articles_fast.bat
```

### 3. Configurar Automação
```bash
# Execute como Administrador
setup_scheduled_task.bat
```

### 4. Monitorar Logs (Automação)
```bash
# Logs ficam em: logs\mark_articles_YYYYMMDD_HHMMSS.log
type logs\mark_articles_*.log
```

## 📈 Exemplo de Execução Rápida

```
[2025-11-02T08:00:00.000Z] Iniciando processo RÁPIDO... [MODO EXECUÇÃO]
[2025-11-02T08:00:00.000Z] 🚀 Versão otimizada - apenas tickets abertos + cache
[2025-11-02T08:00:01.000Z] Cache carregado: 1234 artigos já processados
[2025-11-02T08:00:02.000Z] Total de tickets abertos encontrados: 156
[2025-11-02T08:00:15.000Z] Progresso: 50/156 tickets (32.1%)
[2025-11-02T08:00:28.000Z] Progresso: 100/156 tickets (64.1%)
[2025-11-02T08:00:35.000Z] Progresso: 156/156 tickets (100.0%)

=== RESUMO FINAL (VERSÃO RÁPIDA) ===
Tickets abertos processados: 156/156
Artigos novos processados: 23
Artigos marcados como internal: 8
Cache atualizado: 1257 artigos
Processo concluído em modo otimizado!
```

## 🛠️ Gerenciamento da Tarefa Agendada

### Verificar Status
```bash
schtasks /query /tn "ZammadMarkArticles"
```

### Executar Manualmente
```bash
schtasks /run /tn "ZammadMarkArticles"
```

### Parar Execução
```bash
schtasks /end /tn "ZammadMarkArticles"
```

### Remover Tarefa
```bash
schtasks /delete /tn "ZammadMarkArticles" /f
```

## 🔍 Monitoramento e Troubleshooting

### Verificar Logs
```bash
# Ver último log
dir /od logs\*.log
type logs\mark_articles_20251102_080000.log
```

### Verificar Cache
```bash
# Ver estatísticas do cache
python -c "import json; cache=json.load(open('scripts/processed_articles_cache.json')); print(f'Cache: {len(cache)} artigos')"
```

### Limpar Cache (se necessário)
```bash
del scripts\processed_articles_cache.json
```

## ⚠️ Considerações Importantes

1. **Cache**: O cache acelera muito as execuções, mas pode ser limpo se necessário
2. **Logs**: Logs antigos são automaticamente removidos após 30 dias
3. **Permissões**: Task Scheduler requer privilégios de Administrador para configurar
4. **Monitoramento**: Verifique os logs periodicamente para garantir funcionamento correto

## 🎯 Recomendações de Uso

- **Alta atividade**: Execute a cada 30 minutos
- **Atividade normal**: Execute a cada 1 hora
- **Baixa atividade**: Execute a cada 2-4 horas
- **Primeira vez**: Sempre teste com dry-run primeiro
