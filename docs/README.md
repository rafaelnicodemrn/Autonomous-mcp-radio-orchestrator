# RadioIA — Documentação

> Para os assets referenciados no README principal do projeto (screenshots,
> exemplo de episódio), veja [ASSETS.md](ASSETS.md).

## Visão geral

RadioIA Pessoal é um sistema que gera uma "rádio" personalizada para o Rafael:
coleta conteúdo de diversas fontes (RSS, YouTube, APIs públicas), usa LLMs
(Google Gemini via LiteLLM) para resumir e gerar roteiros em português,
converte para áudio via TTS (Google Cloud Chirp3-HD) e entrega tudo — texto e
áudio — via um bot do Telegram. O bot inclui um sistema adaptativo de
aprendizado que aprende com o feedback do usuário e ajusta a relevância do
conteúdo mostrado ao longo do tempo.

O projeto opera em dois modos:

- **Briefing diário automático** — `telegram_bot.py` dispara
  `send_morning_briefing` todos os dias às 07:00 (horário local), gerando um
  episódio com as fontes de `BRIEFING_SOURCES` e enviando ao chat configurado.
- **On-demand via comandos do Telegram** — comandos como `/noticias`, `/tech`,
  `/fe`, `/gremio`, `/filmes`, `/local`, `/youtube`, `/url` disparam
  `main.py` com as fontes correspondentes e enviam o resultado assim que
  pronto.

## Para quem é esta documentação

- **Você (Claude Code)** em sessões futuras — leia `CLAUDE.md` na raiz do
  projeto primeiro, e use `ai-context/CONTEXT.md` para um resumo denso.
- **Outras IAs** acessando via MCP (`mcp_server.py`) — `ai-context/` foi
  pensado para consumo rápido por IAs.
- **Rafael** revisando, debugando ou evoluindo o projeto.

## Índice da documentação

| Arquivo | Conteúdo |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitetura geral, diagrama ASCII dos componentes e do fluxo de dados |
| [MODULES.md](MODULES.md) | Documentação de cada módulo Python (`telegram_bot.py`, `src/*.py`, `src/sources/youtube.py`) |
| [COMMANDS.md](COMMANDS.md) | Todos os comandos do bot Telegram, com exemplos de uso e saída |
| [CONFIG_GUIDE.md](CONFIG_GUIDE.md) | Referência completa de `config.yaml` (todas as seções e fontes) |
| [ADAPTIVE_SYSTEM.md](ADAPTIVE_SYSTEM.md) | Como funciona o motor de aprendizado adaptativo (5 sinais, pesos dinâmicos) |
| [DATA_FLOWS.md](DATA_FLOWS.md) | Fluxos de dados ponta a ponta — briefing matinal e comando on-demand |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deploy e atualização do bot em uma VM Google Cloud |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Erros comuns observados no projeto e como resolvê-los |
| [ai-context/CONTEXT.md](ai-context/CONTEXT.md) | Resumo denso (≤200 linhas) para consumo por IAs |
| [ai-context/FUNCTIONS_INDEX.md](ai-context/FUNCTIONS_INDEX.md) | Índice de todas as funções do projeto, por arquivo |
| [ai-context/STATE_SCHEMA.md](ai-context/STATE_SCHEMA.md) | Schema dos arquivos JSON de estado (`adaptive_state.json`, `telegram_state.json`) |

## Estado atual do projeto (resumo)

- Sistema de filtragem por perfil (`src/profile_filter.py`) com pontuação via
  Gemini, tradução automática EN→PT, deduplicação e controle de diversidade
  de tópicos.
- Sistema adaptativo de aprendizado (`src/adaptive_engine.py`) com 5 sinais
  ponderados dinamicamente: LLM, reputação de fonte, recência, feedback do
  Telegram (👍/👎) e alinhamento com interesses do YouTube.
- 28 fontes configuradas em `config.yaml` (RSS, YouTube, APIs de
  clima/finanças/futebol/filmes/bíblia/trivia/receitas etc.) e 14 plugins em
  `plugins/`.
- Comandos `/reddit` e `/cultura` foram removidos do bot (a fonte `reddit` e o
  plugin `reddit.py` continuam existindo em `config.yaml`/`plugins/`, mas sem
  comando dedicado).
