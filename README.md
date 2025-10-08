# Zammad Dashboard

Dashboard React para métricas do Zammad com deploy automático via GitHub Pages.

## Funcionalidades

- **Visualização de métricas**: tickets por agente, cliente, estado e prioridade
- **Filtros dinâmicos**: por data, prioridade, estado
- **Gráficos interativos**: barras empilhadas com dados diários
- **Deploy automático**: GitHub Actions atualiza dados diariamente

## Setup

### 1. Configurar Secrets no GitHub
Em Settings → Secrets and variables → Actions:
- `ZAMMAD_TOKEN`: token da API Zammad
- `ZAMMAD_BASE_URL`: URL da instância (opcional, default: https://ufevsuporte.zammad.com)

### 2. Ativar GitHub Pages
Em Settings → Pages → Source: **GitHub Actions**

### 3. Deploy
```bash
git push origin main
```

O workflow executa automaticamente:
- Gera `public/zammad_metrics.json` via Python
- Builda React app
- Publica em GitHub Pages

## Desenvolvimento Local

```bash
# Instalar dependências
npm install

# Gerar dados (requer ZAMMAD_TOKEN)
python scripts/generate_metrics.py

# Executar React
npm start
```

## Estrutura

```
├── .github/workflows/deploy.yml  # GitHub Actions
├── src/                          # React app
├── public/                       # Ficheiros estáticos
├── scripts/generate_metrics.py   # Gerador de dados
└── package.json                  # Dependências React
```

## URL Final
`https://SEU_USER.github.io/SEU_REPO`
