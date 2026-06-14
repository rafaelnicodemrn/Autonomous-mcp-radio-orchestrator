# RadioIA — Contexto Denso para IA

> Resumo compacto (≤200 linhas) para agentes de IA. Para detalhes, ver os
> docs linkados. Índice de funções: [FUNCTIONS_INDEX.md](FUNCTIONS_INDEX.md).
> Schemas de estado: [STATE_SCHEMA.md](STATE_SCHEMA.md).

## O que é

Rádio/podcast pessoal gerado por IA para Rafael. `main.py` lê
`config.yaml: sources:`, busca conteúdo (RSS, YouTube, APIs), resume/roteiriza
com Gemini, sintetiza áudio (Google Cloud TTS, vozes Chirp3-HD em pt-BR) e
grava em `output/<YYYY-MM-DD>/<hora>_<source_id>/` (`episode.json` +
`episode.mp3`). Um bot Telegram (`@radiobootbot`, `telegram_bot.py`) entrega
esse conteúdo como cards individuais com botões de feedback 👍/👎, além de um
briefing matinal automático.

## Processos (3, independentes — ver [DEPLOYMENT.md](../DEPLOYMENT.md))

| Processo | Arquivo | Função |
|---|---|---|
| Player Web | `serve.py` | Interface web, porta 5000 |
| Scheduler | `scheduler.py` | Executa `config.yaml: schedule:` (grade fixa + eventos únicos) |
| Telegram Bot | `telegram_bot.py` | Comandos, briefing 07:00, feedback, aprendizado |

`start_all.bat` inicia os 3 no Windows (cada um em janela própria,
`.venv\Scripts\activate`).

## Arquitetura (ver [ARCHITECTURE.md](../ARCHITECTURE.md))

```
config.yaml ──┬─→ main.py (geração)         ──→ output/<data>/<hora>_<src>/episode.{json,mp3}
              └─→ telegram_bot.py (bot)      ──→ Telegram (@radiobootbot)
                       │
                       ├─ src/profile_filter.py  (filtragem por perfil + Gemini + adaptativo)
                       ├─ src/adaptive_engine.py (5 sinais → score final, pesos dinâmicos)
                       ├─ content_enricher.py    (tradução, imagem, score heurístico, dedup)
                       ├─ telegram_sender.py     (formatação dos cards HTML)
                       └─ src/auth.py            (OAuth YouTube)
```

## Config (`config.yaml`) — ver [CONFIG_GUIDE.md](../CONFIG_GUIDE.md)

- `radio`, `llm` (Gemini), `tts.google` (voice_map para vozes Chirp3-HD),
  `narrators` (Ana=ThalitaMultilingual "descontraída/curiosa/bem-humorada",
  Carlos=Antonio "analítico e direto"), `vinheta` (Francisca, +15% rate),
  `announcements.enabled`, `spots`/`spots_config` (ex. reflexao-crista,
  LLM, 30s, max 2/dia).
- `sources:` — 28 entradas (youtube, noticias, gdelt,
  noticias-internacionais, noticias-locais, catolicismo, conservadorismo,
  biblia, politica, agronegocio, tecnologia, tecnologia-internacional,
  inteligencia-artificial, gremio, copa/brasileirao/libertadores (football),
  utilidades (clima/cotações/sol), efemerides, quiz, receitas, filmes,
  filmes-cartaz, reddit (sem comando no bot), europa, concursos,
  musica-trabalho, musica-noite (disabled)). Quase todas usam
  `model: gemini/gemini-3.1-flash-lite`.
- `schedule:` — Briefing Matinal (07:00 seg-sex), Briefing Fim de Semana
  (08:00 sáb-dom), + 4 eventos únicos da Copa 2026 (fonte `copa`).
- `telegram.perfil` — `nome`, `interesses_primarios` (5),
  `fontes_vip` (4), `ignorar_sempre` (5), `idioma_preferido: pt-BR`,
  `score_minimo_enviar: 5`, `max_cards_por_comando: 8`.
- `telegram.quotas` — por comando, `max_por_fonte`/`max_total` (briefing
  15 total/3 por fonte; demais 8 total/3 por fonte).

## Estado runtime (não versionar valores reais — ver [STATE_SCHEMA.md](STATE_SCHEMA.md))

- `telegram_state.json` — `chat_id`, `last_briefing`, `sent_item_ids`
  (FIFO), `config` (`briefing_time`, `include_audio`,
  `max_items_per_category`).
- `adaptive_state.json` — `source_reputation`, `feedback_history`,
  `youtube_interest_vector`, `command_usage`, `signal_weights`
  (`llm/reputation/recency/feedback/youtube`), `last_youtube_sync`,
  `last_auto_analysis`, `total_items_processed`,
  `total_feedback_given`, `auto_adjustments_log`.

## Sistema adaptativo — ver [ADAPTIVE_SYSTEM.md](../ADAPTIVE_SYSTEM.md)

Score final (0-10) = soma ponderada de 5 sinais: **LLM** (Gemini,
`score_batch_with_gemini`), **reputação** (média histórica por fonte),
**recência** (2/5/7/10 conforme idade), **feedback** (👍/👎 últimos 30 dias),
**YouTube** (alinhamento com `youtube_interest_vector`).
Pesos começam em `{llm:0.70, recency:0.30}` e migram para até
`{llm:0.35, reputation:0.20, recency:0.15, feedback:0.20, youtube:0.10}`
conforme dados se acumulam (`calculate_dynamic_weights`). Recálculo ocorre em
`filter_and_score_items` (passo 4), **só nos comandos on-demand** — o
briefing matinal NÃO passa por esse recálculo.

## Fluxos principais — ver [DATA_FLOWS.md](../DATA_FLOWS.md)

1. **Briefing 07:00**: `send_morning_briefing` → sync YouTube (1x/dia) →
   `main.py` com `BRIEFING_SOURCES` → para cada source_id: enrich → dedup →
   sort → top N (`max_items_per_category`, default 3) → envia cards com
   header de seção. Sem `filter_and_score_items`/quotas/diversity_guard.
2. **Comando on-demand** (ex. `/fe`): `cmd_generate` → `main.py` com fontes
   do comando → busca extra no YouTube por `YOUTUBE_KEYWORDS` →
   `_send_items`: enrich → dedup/sort → `filter_and_score_items` (bloqueio
   por `ignorar_sempre`, score Gemini em lote, recálculo adaptativo,
   `score_minimo_enviar`, `diversity_guard` max 2/tópico) → `_apply_quotas`
   (`telegram.quotas`) → envia até `max_items_per_category*3` (9) cards.
3. **Feedback**: botão 👍/👎 → `callback_feedback` → `record_feedback` →
   atualiza `feedback_history`, `source_reputation`, `signal_weights`.

## Comandos do bot — ver [COMMANDS.md](../COMMANDS.md)

Estáticos: `/start`, `/ajuda`, `/status`, `/historico`, `/perfil [...]`,
`/url <link>`, `/aprendizado`, `/analise`, `/sincronia`, `/config`.
Geração: `/briefing`, `/noticias`, `/tech`, `/fe`, `/gremio`, `/filmes`,
`/local`, `/youtube` — cada um com fontes e `YOUTUBE_KEYWORDS` próprios
(detalhes em COMMANDS.md). `/reddit` e `/cultura` foram removidos (fonte
`reddit` ainda existe em `config.yaml`, sem comando).
Callbacks: `^play:<folder>` (envia mp3), `^fb:<+1|-1>:<hash8>:<src10>:<sid8>:<score>`
(feedback).

## Plugins (`plugins/*.py`)

14 plugins de fonte: `biblia` (ABíbliaDigital), `concursos_pci` (scraping
PCI Concursos), `efemerides` (Wikipedia onthisday), `filmes` (TMDB,
modes trending/now_playing/upcoming/top_rated), `horoscopo`, `receitas`
(TheMealDB + RSS), `reddit` (RSS por subreddit), `trivia` (OpenTDB),
`clipping` (CLI `clipping:<tema>`), `podcast` (RSS + Whisper opcional, CLI
`podcast:<...>`), `url` (artigos via trafilatura + YouTube transcrição),
`whatsapp` (zip export), `gdelt` (4 queries PT, sem auth),
`exemplo_plugin` (template "Frase do Dia").

## Erros conhecidos — ver [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)

`TELEGRAM_BOT_TOKEN` ausente → bot não inicia. `chat_id` ausente → briefing
aborta silenciosamente (precisa `/start`). Credenciais YouTube ausentes →
`/sincronia` degrada graciosamente. Falhas do Gemini → retry 3x com
backoff, fallback neutro. `main.py` tem timeouts (300/360/600s) — fontes
lentas podem ficar de fora. Emojis no console Windows (`cp1252`) →
`UnicodeEncodeError` (não afeta produção). `config.yaml` precisa
`allow_unicode=True` no `yaml.dump`. `callback_data` ≤ 64 bytes UTF-8.

## Segurança / arquivos sensíveis (nunca commitar)

`.env`, `credentials.json`, `token.json`, `google-tts-credentials.json`,
`adaptive_state.json`, `telegram_state.json` (dados pessoais).
