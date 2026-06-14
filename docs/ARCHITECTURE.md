# Arquitetura — RadioIA

## Visão geral

O RadioIA é dividido em três camadas principais:

1. **Geração de episódios** (`main.py` + `src/` + `plugins/`) — coleta
   conteúdo de fontes configuradas em `config.yaml`, gera roteiro com Gemini,
   sintetiza áudio (TTS) e grava o resultado em `output/YYYY-MM-DD/<hora>_<source_id>/`.
2. **Bot do Telegram** (`telegram_bot.py` + `src/profile_filter.py` +
   `src/content_enricher.py` + `src/telegram_sender.py`) — interface do
   usuário: comandos on-demand, briefing automático diário, perfil de
   interesses e botões de feedback.
3. **Sistema adaptativo de aprendizado** (`src/adaptive_engine.py`) —
   ajusta dinamicamente a relevância dos itens com base em reputação de
   fontes, feedback do Telegram e interesses extraídos do YouTube.

Componentes auxiliares: `scheduler.py` (agendamento baseado em
`config.yaml: schedule:`), `serve.py` (interface web) e `mcp_server.py`
(servidor MCP para acesso por outras IAs).

## Diagrama de componentes

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              config.yaml                                    │
│  sources: [youtube, noticias, gdelt, catolicismo, gremio, ...]  (28 fontes) │
│  telegram: { perfil, quotas }       schedule: [...]       llm.model         │
└───────────────┬───────────────────────────────┬────────────────────────────┘
                │                                 │
                ▼                                 ▼
   ┌─────────────────────────┐        ┌──────────────────────────────┐
   │        main.py           │        │       telegram_bot.py          │
   │ (geração de episódios)    │◄──────│ subprocess (_run_main_py)       │
   │                            │       │                                  │
   │ plugins/*.py  src/sources/ │       │ Comandos:                        │
   │   youtube.py rss utility   │       │  /briefing /noticias /tech /fe   │
   │   music ...                │       │  /gremio /filmes /local /youtube │
   │        │                    │       │  /perfil /url /historico /status │
   │        ▼                    │       │  /aprendizado /analise            │
   │ src/script_generator.py     │       │  /sincronia /config /start /ajuda│
   │   (Gemini MODEL_GENERATE)   │       │                                  │
   │        │                    │       │ Job diário 07:00 → briefing       │
   │        ▼                    │       │ Job semanal dom 08:00 → análise   │
   │ src/tts_generator.py        │       └───────────────┬──────────────────┘
   │   (Google TTS Chirp3-HD)    │                       │
   │        │                    │                       ▼
   │        ▼                    │       ┌──────────────────────────────────┐
   │ src/audio_mixer.py          │       │      _send_items / send_morning_  │
   │        │                    │       │             briefing                │
   │        ▼                    │       │  1. enrich_item (content_enricher)  │
   │ output/YYYY-MM-DD/<hora>_   │──────▶│  2. deduplicate                     │
   │   <source_id>/              │ items │  3. filter_and_score_items          │
   │   ├── episode.json          │       │     (profile_filter)                │
   │   └── episode.mp3           │       │       └─ recalcula score via        │
   └─────────────────────────────┘       │          adaptive_engine            │
                                          │  4. _apply_quotas (config.yaml)     │
                                          │  5. diversity_guard (content_enricher)│
                                          │  6. send_item_card (telegram_sender) │
                                          │     + botões 👍/👎 (feedback)        │
                                          └───────────────┬──────────────────────┘
                                                          │
                                                          ▼
                                          ┌──────────────────────────────────┐
                                          │            Telegram                │
                                          │  cards HTML + imagem + botões      │
                                          │  callback_feedback (fb:+1/-1)      │
                                          └───────────────┬──────────────────────┘
                                                          │ record_feedback
                                                          ▼
                                          ┌──────────────────────────────────┐
                                          │       src/adaptive_engine.py        │
                                          │  adaptive_state.json:               │
                                          │   - source_reputation               │
                                          │   - feedback_history                 │
                                          │   - youtube_interest_vector          │
                                          │   - command_usage                    │
                                          │   - signal_weights (dinâmico)        │
                                          └──────────────────────────────────────┘
```

## Componentes principais

### `main.py`
Carrega `config.yaml`, instancia os módulos de coleta (`src/sources/youtube.py`,
`src/sources/rss.py`, `src/sources/music.py`, `src/sources/utility.py` e
plugins dinâmicos em `plugins/*.py` via `_load_plugins()`), gera o roteiro com
`src/script_generator.py` (modelo `llm.model` = `gemini/gemini-3.1-flash-lite`),
sintetiza áudio com `src/tts_generator.py` e mixa com `src/audio_mixer.py`.
Pode ser chamado com uma ou mais `source_id` como argumentos (ex:
`python main.py biblia utilidades catolicismo`) ou com sintaxes especiais como
`url:<link>`, `clipping:<tema>`, `podcast:<url>`.

### `telegram_bot.py`
Bot principal. Mantém `telegram_state.json` (chat_id, último briefing, itens já
enviados). Cada comando de geração (`COMMANDS` dict) dispara `main.py` como
subprocesso, espera o resultado (`_wait_and_collect`, timeout configurável) e
coleta os itens gerados lendo `output/<data>/<pasta>/episode.json`
(`_collect_from_episode_json`). Em seguida passa os itens pelo pipeline de
enriquecimento/filtragem/quotas/envio (`_send_items`). Também agenda o
briefing matinal (07:00) e a análise semanal (domingo 08:00) via `JobQueue`.

### `src/content_enricher.py`
Funções utilitárias de pós-processamento de itens: extração de imagem
(`extract_image`), score básico de relevância (`score_item`), deduplicação por
URL/título (`deduplicate`), controle de diversidade de tópicos
(`diversity_guard`), tradução EN→PT via Gemini (`translate_if_needed`) e o
wrapper de chamadas Gemini com retry (`_gemini_call_with_retry`), reutilizado
por `profile_filter.py` e `adaptive_engine.py`.

### `src/profile_filter.py`
Lê/grava o perfil do usuário (`telegram.perfil` em `config.yaml`). Pipeline
`filter_and_score_items`: bloqueia itens indesejados, pontua em lote via
Gemini (`MODEL_FILTER`), traduz se necessário, recalcula o score final via
`adaptive_engine.compute_adaptive_score`, filtra por `score_minimo_enviar`,
ordena e aplica `diversity_guard`.

### `src/adaptive_engine.py`
Motor de aprendizado adaptativo — ver [ADAPTIVE_SYSTEM.md](ADAPTIVE_SYSTEM.md).
Persiste estado em `adaptive_state.json`.

### `src/telegram_sender.py`
Formatação HTML dos cards de item (`format_item_html`) e funções de envio
(`send_item_card`, `send_audio`, `send_text`, `send_section_header`,
`send_briefing_header`), incluindo emojis/categorias (`SOURCE_EMOJIS`,
`CATEGORY_TITLES`) e hashtags (`_source_tags`).

### `src/sources/youtube.py` + `src/auth.py`
Coleta de vídeos do YouTube (canais configurados + inscrições via OAuth) com
transcrição (`youtube-transcript-api`), estatísticas e comentários. A função
`search_youtube_by_keyword` é usada pelo bot para buscar vídeos relacionados a
um comando (`YOUTUBE_KEYWORDS`). `src/auth.py` gerencia o fluxo OAuth
(`credentials.json` → `token.json`), escopo `youtube.readonly`.

### `plugins/*.py`
Fontes adicionais carregadas dinamicamente por `main.py` se exportarem uma
função `fetch(source_config, credentials=None)`. Exemplos: `biblia.py`
(ABíbliaDigital), `gdelt.py` (notícias via GDELT, sem auth), `filmes.py`
(TMDB), `efemerides.py` (Wikipedia onthisday), `trivia.py` (OpenTDB),
`receitas.py` (TheMealDB + RSS), `concursos_pci.py`, `reddit.py`, `url.py`,
`podcast.py`, `whatsapp.py`, `clipping.py`, `horoscopo.py`,
`exemplo_plugin.py` (template).

### `scheduler.py`, `serve.py`, `mcp_server.py`
- `scheduler.py` — executa `main.py` automaticamente conforme os horários
  definidos em `config.yaml: schedule:` (briefing matinal, fim de semana,
  eventos pontuais da Copa do Mundo 2026).
- `serve.py` — interface web para visualizar/ouvir episódios gerados.
- `mcp_server.py` — expõe o projeto via Model Context Protocol para outras IAs.

## Fluxo de dados resumido

1. `config.yaml` define **o que** coletar (`sources:`) e **quando**
   (`schedule:`), além do perfil e quotas do Telegram (`telegram:`).
2. `main.py` (disparado pelo `scheduler.py` ou pelo `telegram_bot.py` via
   subprocess) coleta + gera roteiro + áudio → grava em `output/`.
3. `telegram_bot.py` lê `output/` (briefing automático) ou aciona `main.py`
   diretamente (comandos on-demand), enriquece/filtra/pontua os itens e envia
   ao Telegram com botões de feedback.
4. Feedback do usuário (👍/👎) e uso de comandos alimentam
   `adaptive_state.json` via `src/adaptive_engine.py`, que recalcula os pesos
   dos sinais e influencia o score dos próximos envios.

Ver [DATA_FLOWS.md](DATA_FLOWS.md) para exemplos passo a passo.
