# Script para Marcar Artigos como Internal

Este script percorre todos os tickets do Zammad e marca como **internal** todos os artigos que **NÃO** tenham emails terminados em `@umafamiliaemviagem.com` nos campos `from`, `to` ou `cc`.

## Como Funciona

1. **Busca todos os tickets** do Zammad
2. **Para cada ticket**, busca todos os artigos
3. **Para cada artigo**, verifica se:
   - Já é interno (se sim, pula)
   - Tem emails `@umafamiliaemviagem.com` nos campos `from`, `to` ou `cc`
4. **Se não tem email do cliente**, marca o artigo como internal

## Modos de Execução

### 1. Modo Teste (Dry-Run) - RECOMENDADO PRIMEIRO
```bash
python scripts\mark_articles_internal.py --dry-run
```
ou execute: `run_mark_articles_internal_test.bat`

- **Não faz alterações reais**
- Mostra quais artigos seriam marcados como internal
- Use para verificar o resultado antes da execução real

### 2. Modo Execução Real
```bash
python scripts\mark_articles_internal.py
```
ou execute: `run_mark_articles_internal.bat`

- **Faz alterações reais no Zammad**
- Marca os artigos como internal permanentemente

## Pré-requisitos

1. **Variáveis de ambiente configuradas**:
   - `ZAMMAD_BASE_URL` (padrão: https://ufevsuporte.zammad.com)
   - `ZAMMAD_TOKEN` (obrigatório)
   - `ZAMMAD_CA_BUNDLE` (opcional)
   - `ZAMMAD_VERIFY_SSL` (opcional, padrão: false)

2. **Dependências Python**:
   - requests
   - re (built-in)
   - datetime (built-in)

## Exemplo de Uso

### Passo 1: Teste primeiro
```bash
# Execute o teste para ver o que seria alterado
run_mark_articles_internal_test.bat
```

### Passo 2: Execute as alterações
```bash
# Se o teste mostrar resultados corretos, execute as alterações
run_mark_articles_internal.bat
```

## Exemplo de Saída

```
[2025-11-02T07:21:00.000Z] Iniciando processo de marcação de artigos como internal... [MODO TESTE (DRY-RUN)]
[2025-11-02T07:21:00.000Z] Domínio do cliente: @umafamiliaemviagem.com
[2025-11-02T07:21:00.000Z] ⚠️  ATENÇÃO: Executando em modo teste - nenhuma alteração será feita!
[2025-11-02T07:21:00.000Z] Buscando todos os tickets...
[2025-11-02T07:21:05.000Z] Total de tickets encontrados: 1542

--- Processando ticket 1542 (1/1542) ---
[2025-11-02T07:21:06.000Z] Encontrados 3 artigos no ticket 1542
[2025-11-02T07:21:06.000Z] Artigo 6353: from='Grupos Newblue PT <grupos@newblue.pt>', to='Suporte UFEV Support <geral@umafamiliaemviagem.com>', cc=''
[2025-11-02T07:21:06.000Z] Artigo 6353 tem email do cliente, mantendo público
[2025-11-02T07:21:06.000Z] [DRY-RUN] Artigo 6354 seria marcado como internal

=== RESUMO FINAL ===
Tickets processados: 1542/1542
Artigos processados: 4626
Artigos marcados como internal: 1234
```

## Critérios de Verificação

O script verifica se há emails `@umafamiliaemviagem.com` nos seguintes campos:
- **from**: Remetente do artigo
- **to**: Destinatário do artigo  
- **cc**: Cópia do artigo

### Exemplos:

**Artigo que PERMANECE público** (tem email do cliente):
```json
{
  "from": "Grupos Newblue PT <grupos@newblue.pt>",
  "to": "Suporte UFEV Support <geral@umafamiliaemviagem.com>",
  "cc": null
}
```

**Artigo que é marcado como INTERNAL** (não tem email do cliente):
```json
{
  "from": "sistema@zammad.com",
  "to": "agente@empresa.com", 
  "cc": null
}
```

## Segurança

- **Sempre execute o modo teste primeiro** para verificar os resultados
- O script mantém todos os campos originais do artigo, apenas altera `internal: true`
- Logs detalhados mostram cada operação realizada
- Em caso de erro, o script continua com os próximos artigos

## Limitações

- O script processa **todos os tickets**, o que pode demorar bastante tempo
- Requer permissões de API para ler tickets/artigos e atualizar artigos
- Não há função de "desfazer" - faça backup se necessário
