# Índice de Funções — RadioIA

Índice de referência rápida das funções dos arquivos documentados em
[MODULES.md](../MODULES.md). Para explicações detalhadas, ver MODULES.md,
[ADAPTIVE_SYSTEM.md](../ADAPTIVE_SYSTEM.md) e
[DATA_FLOWS.md](../DATA_FLOWS.md).

## `telegram_bot.py`

| Função | Descrição |
|---|---|
| `load_state()` / `save_state(state)` | Lê/grava `telegram_state.json`, com FIFO de `sent_item_ids` (máx 500) |
| `item_hash(item)` | `md5(f"{source_id}/{id ou title}")[:12]` |
| `_collect_from_episode_json(source_ids)` | Lê `output/<hoje>/*/episode.json` e monta lista de itens |
| `_run_main_py(sources)` | `Popen([python, 'main.py', *sources])` |
| `_wait_and_collect(proc, sources, timeout=300)` | Aguarda subprocesso (kill se timeout) e coleta itens |
| `load_quotas(cmd_key=None)` | Lê `telegram.quotas` do `config.yaml` |
| `_fetch_youtube_for_cmd(cmd_key)` | Busca vídeos extras via `YOUTUBE_KEYWORDS[cmd_key]` |
| `cmd_start` / `cmd_ajuda` | `/start`, `/ajuda` — registra chat_id, lista comandos |
| `cmd_status` | `/status` — chat_id, último briefing, histórico, próximo horário |
| `cmd_historico` | `/historico` — episódios de hoje com botões play |
| `callback_play` | callback `play:` — envia `episode.mp3` |
| `callback_feedback` | callback `fb:` — chama `record_feedback`, remove teclado |
| `cmd_aprendizado` | `/aprendizado` — `format_learning_status(load_adaptive_state())` |
| `cmd_analise` | `/analise` — `run_weekly_analysis` sob demanda |
| `cmd_sincronia` | `/sincronia` — força `sync_youtube_signals` |
| `cmd_config` | `/config` — mostra quotas e `signal_weights` |
| `weekly_analysis_job` | Job dom 08:00 — roda e envia `run_weekly_analysis` |
| `cmd_perfil` | `/perfil [...]` — visualiza/edita perfil |
| `cmd_url` | `/url <link>` — roda `main.py "url:<link>"` |
| `cmd_generate(update, context, sources, label, cmd_key='')` | Handler genérico dos comandos de `COMMANDS` |
| `_build_feedback_keyboard(item)` | Monta `InlineKeyboardMarkup` com botões `fb:+1/-1:...` |
| `_apply_quotas(items, cmd_key)` | Aplica `max_por_fonte`/`max_total` de `telegram.quotas` |
| `_send_items(bot, chat_id, items, cmd_key='')` | Pipeline completo: enrich → dedup → filter → quotas → envio |
| `send_morning_briefing(context)` | Job diário 07:00 — sync YouTube + briefing por seções |
| `_set_env_chat_id(chat_id)` | Grava `TELEGRAM_CHAT_ID` no `.env` |
| `_make_command_handler(sources, label, cmd_key)` | Factory de `CommandHandler` |
| `main()` | Valida token, registra handlers/jobs, inicia o bot |

## `src/content_enricher.py`

| Função | Descrição |
|---|---|
| `extract_image(url, item)` | Extrai imagem (cache, thumbnail YouTube, og:image, fallback) |
| `_extract_from_item(item)` | Fallback de imagem a partir do próprio item |
| `_save_img_cache(path, value)` | Persiste cache de imagens |
| `score_item(item)` | Score heurístico 0–10 (keywords, fonte confiável, recência, mídia) |
| `_normalize_title(title)` | Normaliza título para comparação (lowercase, remove stopwords PT) |
| `deduplicate(items)` | Remove duplicatas por URL e por similaridade de título (≥0.55) |
| `_detect_topic(item)` | Detecta tópico (`copa`, `gremio`, `ia`, `papa`, `politica_br`, `economia`) |
| `diversity_guard(items, max_per_topic=2)` | Limita itens por tópico detectado |
| `_load_trans_cache()` / `_save_trans_cache(cache)` | Cache de traduções (`TRANS_CACHE_FILE`) |
| `_is_english(text)` | Heurística de detecção de inglês (≥4 palavras comuns) |
| `_gemini_call_with_retry(prompt, model, max_tokens)` | Wrapper com retry/backoff/timeout sobre `litellm.completion` — reutilizado por `profile_filter.py` e `adaptive_engine.py` |
| `translate_if_needed(title, text)` | Traduz EN→PT via Gemini, com cache |
| `enrich_item(item)` | Aplica tradução + imagem + score; retorna item enriquecido |

## `src/profile_filter.py`

| Função | Descrição |
|---|---|
| `load_profile()` | Lê `telegram.perfil` (com fallback/validação) |
| `_default_profile()` | Perfil padrão do Rafael |
| `_validate_profile(perfil)` | Completa chaves ausentes com defaults |
| `save_profile(profile)` | Grava `telegram.perfil` em `config.yaml` (`allow_unicode=True`) |
| `should_block(item, profile)` | Verifica `ignorar_sempre` |
| `score_batch_with_gemini(items, profile)` | Pontua lotes de 5 itens via Gemini (`MODEL_FILTER`) |
| `filter_and_score_items(items, profile)` | Pipeline de 7 passos: bloqueio → score Gemini → tradução → recálculo adaptativo → filtro por `score_minimo_enviar` → ordenação → `diversity_guard` |
| `format_profile(profile)` | HTML para `/perfil` |
| `format_help()` | HTML para `/perfil ajuda` |

## `src/telegram_sender.py`

| Função | Descrição |
|---|---|
| `_escape_html(text)` | Escapa `&`, `<`, `>` |
| `_stars(score)` | `⭐⭐` (≥8), `⭐` (≥5), ou vazio |
| `_extract_bullets(text, max_bullets=3)` | Extrai bullets do texto (existentes ou por frases) |
| `_source_tags(source_id, source_name)` | Gera até 3 hashtags por fonte/tipo |
| `format_item_html(item, enriched)` | Monta card HTML (cabeçalho, título, bullets, link, tags) |
| `send_item_card(bot, chat_id, item, enriched, reply_markup=None)` | Envia foto+caption (fallback texto) |
| `send_audio(bot, chat_id, mp3_path, caption)` | Envia `episode.mp3` |
| `send_section_header(bot, chat_id, source_id)` | Separador + `CATEGORY_TITLES[source_id]` |
| `send_briefing_header(bot, chat_id, weather_text='', finance_text='', verse='')` | Cabeçalho do briefing matinal |
| `send_text(bot, chat_id, text, parse_mode='HTML', disable_preview=True)` | Envio de texto simples |

## `src/adaptive_engine.py`

Documentação completa do funcionamento em [ADAPTIVE_SYSTEM.md](../ADAPTIVE_SYSTEM.md);
schema do estado em [STATE_SCHEMA.md](STATE_SCHEMA.md).

| Função | Descrição |
|---|---|
| `load_adaptive_state()` / `save_adaptive_state(state)` | Lê/grava `adaptive_state.json`, com backfill de chaves do `DEFAULT_STATE` |
| `_calc_recency(published_at)` | Score de recência: hoje=10, ontem=7, 2 dias=5, 3+=2, inválido=5 |
| `_calc_feedback_score(source_name, state)` | Score 0–10 a partir de `feedback_history` dos últimos `FEEDBACK_WINDOW_DAYS` (30) para a fonte; sem histórico=5.0 |
| `_calc_youtube_alignment(item, state)` | Alinhamento com `youtube_interest_vector` (5.0 se vetor vazio; 0–10 conforme matches; 0.0 se vetor não-vazio sem match) |
| `update_source_reputation(source_name, score, state)` | Atualiza média móvel em `source_reputation[source_name]['avg']` |
| `compute_adaptive_score(item, gemini_score, state)` | Combina os 5 sinais via `signal_weights`, clamp 0–10 |
| `calculate_dynamic_weights(state)` | Calcula `signal_weights` conforme estágio de dados acumulados (5 tiers) |
| `record_feedback(item_hash, src_short, sid_short, gemini_score, feedback)` | Registra feedback, atualiza reputação e pesos, salva estado |
| `record_command_usage(cmd_key)` | Incrementa `command_usage[cmd_key]` |
| `sync_youtube_signals(youtube_service)` | Busca liked/histórico do YouTube, pede vetor de interesses ao Gemini |
| `run_weekly_analysis(state)` | Gera relatório semanal via Gemini (requer ≥3 feedbacks ou reputação não-vazia) |
| `format_learning_status(state)` | HTML para `/aprendizado` |

## `src/sources/youtube.py`

| Função | Descrição |
|---|---|
| `_build_client(api_key, credentials=None)` | Cliente YouTube (OAuth ou `developerKey`) |
| `_get_uploads_playlist_id(youtube, channel_id)` | Playlist de uploads do canal |
| `_get_recent_videos(youtube, playlist_id, max_results, days_lookback)` | Vídeos recentes filtrados |
| `_enrich_with_stats(youtube, videos)` | Adiciona `views` e `description` |
| `_get_top_comments(api_key, video_id, max_comments=5)` | Top 3 comentários (via API key) |
| `_try_get_transcript(video_id, lang_pref)` | Transcrição (até `MAX_TRANSCRIPT_CHARS=600`) |
| `_fetch_from_channels(youtube, api_key, channels, max_per_channel, days_lookback, max_total, lang_pref)` | Coleta vídeos de canais configurados |
| `get_subscription_channels(youtube, max_channels=50)` | Lista canais inscritos (OAuth) |
| `fetch(source_config, credentials=None)` | Entrada principal — combina inscrições + canais configurados |
| `search_youtube_by_keyword(query, youtube_service, max_results=3, published_after_hours=48)` | Busca por palavra-chave, últimas N horas |

## `src/auth.py`

| Função | Descrição |
|---|---|
| `get_youtube_credentials()` | Retorna `Credentials` válidas (refresh/`InstalledAppFlow`) ou `None` se `credentials.json` ausente |

## Plugins (`plugins/*.py`)

Todos exportam `fetch(source_config, credentials=None) -> list[dict]`. Ver
tabela completa em [MODULES.md](../MODULES.md#plugins).

| Arquivo | Função principal |
|---|---|
| `biblia.py` | `fetch` — passagem bíblica via ABíbliaDigital |
| `gdelt.py` | `fetch` — notícias GDELT (4 queries PT) |
| `efemerides.py` | `fetch` — "Hoje na História" via Wikipedia onthisday |
| `filmes.py` | `fetch`, `_get_genres` — filmes via TMDB (trending/now_playing/upcoming/top_rated) |
| `trivia.py` | `fetch` — perguntas via OpenTDB |
| `receitas.py` | `fetch` — receita via TheMealDB + RSS |
| `concursos_pci.py` | `fetch`, `_parse_date` — scraping PCI Concursos |
| `reddit.py` | `fetch`, `_clean_summary` — top posts via RSS por subreddit |
| `horoscopo.py` | `fetch` — horóscopo por pares de signos |
| `url.py` | `fetch`, `_youtube_video_id`, `_fetch_youtube` — extrai conteúdo de URL/YouTube |
| `podcast.py` | `fetch` — transcrição/resumo de podcast via Whisper |
| `clipping.py` | `fetch` — cobertura de um tema em múltiplos veículos |
| `whatsapp.py` | `fetch` — resumo de exportações `.zip` do WhatsApp |
| `exemplo_plugin.py` | `fetch` — template "Frase do Dia" |
