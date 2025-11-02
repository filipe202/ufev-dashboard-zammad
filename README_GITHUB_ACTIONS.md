# GitHub Actions - Automação Zammad

Configuração para executar automaticamente o script de marcação de artigos usando GitHub Actions.

## 🚀 Vantagens do GitHub Actions

- **Gratuito**: 2000 minutos/mês para repositórios privados
- **Confiável**: Infraestrutura da Microsoft/GitHub
- **Logs completos**: Histórico de todas as execuções
- **Sem manutenção**: Não precisa de servidor próprio
- **Flexível**: Múltiplos horários e configurações

## 📁 Workflows Criados

### 1. `mark-articles-internal.yml` - Principal
- **Frequência**: A cada hora
- **Cron**: `0 * * * *`
- **Uso**: Execução padrão contínua

### 2. `mark-articles-frequent.yml` - Horário Comercial  
- **Frequência**: A cada 30 minutos
- **Cron**: `*/30 7-17 * * 1-5` (Seg-Sex, 8h-18h Portugal)
- **Uso**: Alta frequência durante expediente

## ⚙️ Configuração Inicial

### Passo 1: Configurar Secrets

No GitHub, vá em **Settings > Secrets and variables > Actions** e adicione:

| Secret | Valor | Descrição |
|--------|-------|-----------|
| `ZAMMAD_TOKEN` | `1qbRbHElT2yBzhPPc7sFnE-BQITXT9asONjyx_rH6DyJc-U5JJ7CYWcfWmVa6s2x` | Token da API Zammad |
| `ZAMMAD_BASE_URL` | `https://ufevsuporte.zammad.com` | URL base do Zammad |

### Passo 2: Fazer Push dos Workflows

```bash
git add .github/
git commit -m "Add GitHub Actions workflows for Zammad automation"
git push
```

### Passo 3: Verificar Execução

1. Vá em **Actions** no GitHub
2. Veja os workflows listados
3. Execute manualmente para testar

## 🕐 Horários de Execução

### Workflow Principal (Hourly)
```yaml
schedule:
  - cron: '0 * * * *'  # A cada hora
```

### Workflow Frequente (Business Hours)
```yaml
schedule:
  - cron: '*/30 7-17 * * 1-5'  # Seg-Sex, 8h-18h Portugal, a cada 30min
```

### Personalizar Horários

Para alterar os horários, edite o campo `cron` nos arquivos `.yml`:

```yaml
# Exemplos de cron expressions
'0 */2 * * *'      # A cada 2 horas
'*/15 9-17 * * 1-5' # A cada 15min, 9h-17h, Seg-Sex
'0 9,12,15,18 * * *' # 4x por dia: 9h, 12h, 15h, 18h
```

## 🔧 Execução Manual

### Via Interface GitHub
1. Vá em **Actions**
2. Selecione o workflow
3. Clique **Run workflow**
4. Escolha **dry-run** para teste

### Via GitHub CLI
```bash
# Executar em modo teste
gh workflow run mark-articles-internal.yml -f dry_run=true

# Executar em modo produção
gh workflow run mark-articles-internal.yml -f dry_run=false
```

## 📊 Monitoramento

### Ver Logs de Execução
1. **Actions** > Selecionar execução
2. Expandir job **mark-articles**
3. Ver logs detalhados de cada step

### Download de Artifacts
- Logs são salvos como artifacts
- Cache é preservado entre execuções
- Retenção: 30 dias

### Exemplo de Log
```
🚀 Executando em modo produção...
[2025-11-02T08:00:00.000Z] Iniciando processo RÁPIDO... [MODO EXECUÇÃO]
[2025-11-02T08:00:01.000Z] Cache carregado: 1234 artigos já processados
[2025-11-02T08:00:02.000Z] Total de tickets abertos encontrados: 156
[2025-11-02T08:00:35.000Z] Processo concluído em modo otimizado!
```

## 🔄 Cache Automático

O cache é automaticamente:
- **Carregado** no início de cada execução
- **Atualizado** durante o processamento  
- **Commitado** de volta ao repositório
- **Sincronizado** entre execuções

### Estrutura do Cache
```json
{
  "12345": {
    "processed_at": "2025-11-02T08:00:00.000Z",
    "was_internal": false,
    "action": "marked_internal"
  }
}
```

## 🚨 Troubleshooting

### Erro: "Context access might be invalid"
- **Causa**: Secrets não configurados
- **Solução**: Adicionar `ZAMMAD_TOKEN` e `ZAMMAD_BASE_URL` nos Secrets

### Erro: "Authentication failed"
- **Causa**: Token inválido ou expirado
- **Solução**: Gerar novo token no Zammad e atualizar Secret

### Workflow não executa
- **Causa**: Repositório inativo por 60 dias
- **Solução**: Fazer qualquer commit para reativar

### Cache não persiste
- **Causa**: Erro no commit automático
- **Solução**: Verificar permissões do repositório

## 📈 Otimizações Implementadas

### Performance
- ✅ Apenas tickets abertos
- ✅ Cache inteligente
- ✅ Timeouts otimizados
- ✅ Processamento paralelo

### Confiabilidade  
- ✅ Retry automático em falhas
- ✅ Logs detalhados
- ✅ Artifacts preservados
- ✅ Cache persistente

### Segurança
- ✅ Secrets criptografados
- ✅ Tokens não expostos em logs
- ✅ Ambiente isolado por execução

## 💰 Custos GitHub Actions

### Repositório Público
- **Gratuito**: Ilimitado

### Repositório Privado
- **Gratuito**: 2000 minutos/mês
- **Estimativa**: ~2-3 min/execução
- **Capacidade**: ~600-1000 execuções/mês

### Cálculo para Diferentes Frequências

| Frequência | Execuções/mês | Minutos/mês | Status |
|------------|---------------|-------------|--------|
| A cada hora | ~720 | ~1440-2160 | ✅ Dentro do limite |
| A cada 30min | ~1440 | ~2880-4320 | ⚠️ Pode exceder |
| A cada 15min | ~2880 | ~5760-8640 | ❌ Excede limite |

## 🎯 Recomendações

### Para Alta Atividade
```yaml
# Horário comercial: a cada 30min
# Fora do horário: a cada 2h
schedule:
  - cron: '*/30 8-18 * * 1-5'  # Comercial
  - cron: '0 */2 * * *'        # 24/7 baixa freq
```

### Para Atividade Normal
```yaml
# A cada hora durante o dia
schedule:
  - cron: '0 8-20 * * *'
```

### Para Baixa Atividade
```yaml
# 3x por dia
schedule:
  - cron: '0 9,14,18 * * 1-5'
```

## 🔧 Comandos Úteis

### Verificar Status
```bash
gh run list --workflow=mark-articles-internal.yml
```

### Ver Logs da Última Execução
```bash
gh run view --log
```

### Cancelar Execução
```bash
gh run cancel <run-id>
```

### Baixar Artifacts
```bash
gh run download <run-id>
```
