# RadioIA — Contexto para Claude Code

## O que é
Rádio pessoal com IA do Rafael (Product Owner, Medianeira/PR, católico conservador,
torcedor do Grêmio, cidadão BR + LU). Coleta conteúdo de RSS, YouTube e APIs
diversas → LLM (Gemini via LiteLLM) resume e gera roteiro → TTS (Google Cloud
Chirp3-HD) gera áudio → Telegram entrega texto/áudio com sistema adaptativo de
aprendizado que ajusta o que é mostrado com base no comportamento do usuário.

## Stack
- Python 3.11
- LiteLLM (`litellm.completion`) → Google Gemini
  - **Filtragem/scoring** (alto volume, barato): `gemini/gemini-2.5-flash-lite`
  - **Geração de roteiro/conteúdo** (qualidade PT-BR): `gemini/gemini-3.1-flash-lite`
- python-telegram-bot 22.x (Application, JobQueue, CallbackQueryHandler)
- PyYAML para `config.yaml`
- Google Cloud TTS (Chirp3-HD) com fallback edge-tts
- google-api-python-client + google-auth-oauthlib (YouTube Data API v3, OAuth `youtube.readonly`)
- tenacity para retries em chamadas Gemini
- feedparser, BeautifulSoup, trafilatura para coleta/extração de conteúdo

## Estrutura do projeto
```
radioIA/
├── main.py                  # Gera episódios (RSS/YouTube/plugins → LLM → TTS → output/)
├── telegram_bot.py           # Bot Telegram (comandos, briefing, feedback, aprendizado)
├── scheduler.py               # Agendador baseado em config.yaml: schedule:
├── serve.py / mcp_server.py    # Interface web / servidor MCP
├── config.yaml                # Configuração central (fontes, perfil, schedule, telegram)
├── adaptive_state.json        # Estado do motor de aprendizado adaptativo
├── telegram_state.json        # Estado operacional do bot (chat_id, histórico enviado)
├── src/
│   ├── adaptive_engine.py     # Motor de aprendizado adaptativo (5 sinais)
│   ├── profile_filter.py      # Filtro/score por perfil + integração com adaptive_engine
│   ├── content_enricher.py    # Enriquecimento: imagem, score, dedup, diversidade, tradução
│   ├── telegram_sender.py      # Formatação/envio de mensagens HTML para o Telegram
│   ├── auth.py                 # OAuth do YouTube (credentials.json/token.json)
│   └── sources/youtube.py      # Plugin de coleta do YouTube (canais + busca por keyword)
├── plugins/                    # Fontes adicionais (biblia, gdelt, filmes, receitas, etc.)
└── docs/                       # Documentação completa (ver docs/README.md)
```

## Modelos
- **Filtragem** (`profile_filter.score_batch_with_gemini`, traduções, análises do
  `adaptive_engine`): `gemini/gemini-2.5-flash-lite` (constante `MODEL_FILTER`,
  configurável via env `TELEGRAM_LLM_MODEL`)
- **Geração** (roteiros de episódio via `main.py`, todas as `sources:` do
  `config.yaml`): `gemini/gemini-3.1-flash-lite` (`llm.model` em `config.yaml`,
  constante `MODEL_GENERATE` em `telegram_bot.py`)

## Comandos do bot (visão rápida)
`/briefing` `/noticias` `/tech` `/fe` `/gremio` `/filmes` `/local` `/youtube`
`/perfil` `/url` `/historico` `/status` `/aprendizado` `/analise` `/sincronia`
`/config` `/start` `/ajuda` — detalhes completos em `docs/COMMANDS.md`.

## Sistema adaptativo
O bot ajusta o score final dos itens combinando 5 sinais (LLM, reputação de
fonte, recência, feedback do Telegram, alinhamento com interesses do YouTube)
com pesos dinâmicos. Detalhes em `docs/ADAPTIVE_SYSTEM.md` e
`docs/ai-context/STATE_SCHEMA.md`.

## Convenções importantes
- Python 3.11 no Windows: **não usar aspas iguais aninhadas dentro de f-strings**
  (ex: defina `sep = '━' * 20` antes, não `f"{'━' * 20}"`).
- `config.yaml` é lido/escrito com `yaml.safe_load`/`yaml.dump(allow_unicode=True,
  default_flow_style=False, sort_keys=False)` — preserva acentos e ordem.
- Estado persistido em JSON na raiz (`adaptive_state.json`, `telegram_state.json`)
  com `ensure_ascii=False, indent=2`.
- `callback_data` do Telegram tem limite de 64 bytes UTF-8 — payloads de feedback
  usam hashes/abreviações curtas (`fb:+1:<hash8>:<src10>:<sid8>:<score>`).
- Chamadas ao Gemini usam `_gemini_call_with_retry` (tenacity, 3 tentativas,
  backoff exponencial 2–8s, `reraise=False`, timeout 15s).

## Não fazer
- Não reintroduzir `/reddit` ou `/cultura` no `telegram_bot.py` (removidos
  intencionalmente; o plugin `reddit.py` e a fonte `reddit` continuam em
  `config.yaml` mas não têm comando dedicado).
- Não commitar `credentials.json`, `token.json`, `google-tts-credentials.json`
  ou `.env`.

## CI/CD
Fluxo: push → GitHub Actions CI (lint + testes) → merge na `main` → CD (rsync +
restart systemd).
- CI: `.github/workflows/ci.yml` — jobs `lint` (black/isort/flake8,
  bloqueante; config compartilhada em `pyproject.toml` e per-file-ignores em
  `setup.cfg`), `test` (pytest, com checagem de credenciais commitadas) e
  `security` (bandit + pip-audit, `|| true`).
- CD: `.github/workflows/cd.yml` — roda em push para `main`, reusa o CI,
  faz rsync para a VM (excluindo `config.yaml`, `adaptive_state.json`,
  `telegram_state.json`, `*.json`) e reinicia `radioia-bot` via systemd, com
  rollback automático em caso de falha.
- Verificação semanal: `.github/workflows/weekly-check.yml` (dependências
  desatualizadas + `pip-audit`).
- Testes: `pytest tests/` (smoke → unit → integration), config em `pytest.ini`.
  Cobertura mínima atual: 20% (`--cov-fail-under=20`); meta é subir ~5% por
  sprint até 60%, conforme `tests/` crescer.
- Setup do servidor para CD (chaves SSH dedicadas, sudoers, secrets do
  GitHub, environment `production`): ver `docs/CI_CD_SETUP.md`.

### Para adicionar um novo módulo
1. Criar o módulo em `src/`
2. Criar `tests/unit/test_[modulo].py` com `TestClass` cobrindo as funções
   principais
3. Adicionar import no `tests/smoke/test_imports.py`
4. Commit: `feat(src): adiciona módulo X`

### Deploy manual de emergência
```
ssh rafaelnicodemrn@34.24.139.45
cd ~/radioIA && git pull && sudo systemctl restart radioia-bot
```

### Rollback manual
```
cd ~/radioIA && git log --oneline -5
git checkout <commit_anterior> -- .
sudo systemctl restart radioia-bot
```

## Documentação completa
Ver `docs/README.md` para o índice completo (arquitetura, módulos, comandos,
config, sistema adaptativo, fluxos de dados, deploy, troubleshooting) e
`docs/ai-context/CONTEXT.md` para um resumo denso voltado a IAs.
