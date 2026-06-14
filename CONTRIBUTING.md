# Contribuindo com o RadioIA

## Setup do ambiente local

```bash
git clone https://github.com/fabianoallex/radioIA.git
cd radioIA

# venv
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # Linux/macOS

pip install -r requirements.txt -r requirements-dev.txt
```

### Configuração

1. Copie `config.yaml.example` para `config.yaml` e ajuste fontes, perfil e
   agendamento conforme necessário.
2. Crie um arquivo `.env` na raiz com as variáveis necessárias (tokens do
   Telegram, chaves de API do Gemini etc.) — **nunca commitar** este arquivo.
3. Para TTS via Google Cloud, coloque o JSON de credenciais fora do repositório
   e aponte `GOOGLE_APPLICATION_CREDENTIALS` para ele.

### Rodando os testes

```bash
make test       # suíte completa (smoke + unit + integration)
make smoke      # apenas smoke tests (importações)
make coverage   # relatório HTML de cobertura em htmlcov/
make lint       # flake8 + black + isort
```

## Estratégia de branches

```
main        ← produção (protegida, sem push direto)
develop     ← integração (base para PRs de features)
feature/*   ← novas funcionalidades (ex: feature/adaptive-weights-v2)
fix/*       ← correções de bug (ex: fix/telegram-callback-limit)
hotfix/*    ← correções urgentes direto para main + develop
```

Abra PRs de `feature/*`/`fix/*` para `develop`. Releases vão de `develop`
para `main` via PR.

## Convenção de commits

Este projeto usa [Conventional Commits](https://www.conventionalcommits.org/).
Veja `.github/commit-convention.md` para referência rápida e exemplos.

## Pull Requests

- Use o template em `.github/PULL_REQUEST_TEMPLATE.md`.
- Garanta que `pytest tests/` passa localmente.
- Não inclua arquivos de credencial (`.env`, `*credentials*.json`, `token.json`,
  `adaptive_state.json`, `telegram_state.json`).
- O CI (lint + testes + verificação de segredos) precisa passar antes do merge.
