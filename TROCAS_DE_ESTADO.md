# Indicador de Trocas de Estado por Agente

## Descrição
Este novo indicador rastreia o número de trocas de estado que cada utilizador/agente fez por dia. Os dados são agregados por utilizador e podem ser filtrados por prioridade.

## Como Funciona

### Coleta de Dados (Backend - Python)
O script `scripts/generate_metrics.py` foi modificado para:
1. Buscar o histórico de cada ticket através da API do Zammad (`/api/v1/tickets/{ticket_id}/history`)
2. Identificar mudanças no campo `state_id` (trocas de estado)
3. Registrar quem fez cada troca (campo `created_by_id`)
4. Agregar os dados por agente e por dia
5. Permitir filtragem por prioridade do ticket

### Visualização (Frontend - React)
A interface em `src/App.js` foi atualizada com:
1. Novo botão de navegação "Trocas de Estado"
2. Página dedicada com:
   - Filtro de prioridade
   - Gráfico de barras horizontais mostrando total de trocas por agente
   - Ranking dos agentes com mais trocas
   - Gráfico temporal mostrando trocas por dia
   - Explicação da métrica

## Como Usar

### 1. Gerar os Dados
Execute o script Python para coletar os dados do Zammad:
```bash
cd "c:\Users\filipe.correia\Zammad dashboard"
python scripts/generate_metrics.py
```

**Nota**: Este processo pode demorar mais tempo do que antes, pois agora busca o histórico de cada ticket individualmente.

### 2. Visualizar no Dashboard
1. Acesse o dashboard no navegador
2. Clique no botão "Trocas de Estado" no menu de navegação
3. Use o filtro de prioridade para ver apenas trocas em tickets específicos (P1, P2, P3, etc.)

## Interpretação dos Dados

- **Mais trocas** = agente mais ativo na gestão de estados dos tickets
- **Filtro por prioridade** = permite identificar quem trabalha mais em tickets de alta prioridade
- **Distribuição temporal** = mostra em que dias houve mais atividade de gestão de estados

## Estrutura dos Dados

Os dados são armazenados em `src/zammad_metrics.js` no formato:
```javascript
"agent_state_changes": {
  "Nome do Agente": {
    "overall": {
      "tickets_count": 150,  // Total de trocas
      "tickets_per_day": {
        "2025-10-01": 10,
        "2025-10-02": 15,
        // ...
      }
    },
    "priorities": {
      "P1": { /* mesma estrutura */ },
      "P2": { /* mesma estrutura */ },
      // ...
    }
  }
}
```

## Cores e Design
- Cor principal: **Roxo** (#8b5cf6) - diferencia este indicador dos outros
- Layout similar aos outros indicadores para consistência
- Responsivo para dispositivos móveis
