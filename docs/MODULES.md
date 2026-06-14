# Módulos — RadioIA

Documentação módulo a módulo dos arquivos lidos para esta documentação:
`telegram_bot.py`, `src/adaptive_engine.py`, `src/profile_filter.py`,
`src/content_enricher.py`, `src/telegram_sender.py`, `src/sources/youtube.py`,
`src/auth.py` e os plugins em `plugins/`.

---

## `telegram_bot.py`

Bot principal do Telegram. Ponto de entrada: `python telegram_bot.py`.

### Constantes
- `MODEL_FILTER = 'gemini/gemini-2.5-flash-lite'` — não usado diretamente neste
  arquivo (mantido para referência/consistência com `profile_filter.py`).
- `MODEL_GENERATE = 'gemini/gemini-3.1-flash-lite'` — idem, referência ao
  modelo de geração usado por `main.py`.
- `BOT_TOKEN` — `TELEGRAM_BOT_TOKEN` do `.env`.
- `STATE_FILE = 'telegram_state.json'`
- `MAX_SENT_IDS = 500` — tamanho máximo do histórico FIFO de itens enviados.
- `MAX_ITEMS_PER_CATEGORY = 3`
- `BRIEFING_HOUR = 7`, `BRIEFING_MINUTE = 0` — horário do briefing automático.
- `BRIEFING_SOURCES` — fontes incluídas no briefing matinal:
  `['biblia', 'utilidades', 'catolicismo', 'noticias', 'tecnologia', 'politica', 'conservadorismo']`.
- `COMMANDS` — mapeia cada comando de geração para a lista de `source_id`
  passada a `main.py`:

  | Comando | Fontes |
  |---|---|
  | `/briefing` | biblia, utilidades, catolicismo, noticias, tecnologia, politica, conservadorismo, gdelt |
  | `/noticias` | noticias, politica, noticias-internacionais, gdelt |
  | `/tech` | tecnologia, inteligencia-artificial, tecnologia-internacional |
  | `/fe` | biblia, catolicismo, conservadorismo |
  | `/gremio` | gremio, copa, brasileirao, libertadores |
  | `/filmes` | filmes, filmes-cartaz |
  | `/local` | noticias-locais, agronegocio |
  | `/youtube` | youtube |

- `YOUTUBE_KEYWORDS` — por comando, lista de queries usadas em
  `search_youtube_by_keyword` para trazer vídeos extras relacionados ao tema
  (ex: `/fe` → `['catolicismo reflexão', 'Padre Paulo Ricardo']`).

### Estado (`telegram_state.json`)
- `load_state()` / `save_state(state)` — leitura/gravação com FIFO de
  `sent_item_ids` limitado a `MAX_SENT_IDS`. Schema completo em
  [STATE_SCHEMA.md](ai-context/STATE_SCHEMA.md).
- `item_hash(item)` — `md5(f"{source_id}/{id ou title}")[:12]`, usado para
  marcar itens já enviados.

### Coleta de conteúdo
- `_collect_from_episode_json(source_ids)` — lê `output/<hoje>/*/episode.json`
  e converte `links` em itens (`title`, `url`, `text`, `source_name`,
  `source_id`, `source_type`, `published_at`, `views`, `_audio_path`,
  `_episode_folder`).
- `_run_main_py(sources)` — `subprocess.Popen([python, 'main.py', *sources])`,
  roda em background.
- `_wait_and_collect(proc, sources, timeout=300)` — aguarda o processo (com
  timeout, matando-o se exceder) e chama `_collect_from_episode_json`.
- `load_quotas(cmd_key=None)` — lê `telegram.quotas` do `config.yaml`; se
  `cmd_key` informado, retorna só a quota daquele comando (sem `/`).
- `_fetch_youtube_for_cmd(cmd_key)` — para comandos em `YOUTUBE_KEYWORDS`,
  obtém credenciais OAuth (`src.auth.get_youtube_credentials`), monta o
  client (`googleapiclient.discovery.build`) e chama
  `search_youtube_by_keyword` para cada keyword (até 2 resultados cada).
  Retorna `[]` silenciosamente em qualquer falha.

### Handlers de comando

| Função | Comando | Resumo |
|---|---|---|
| `cmd_start` | `/start` | Registra `chat_id`, atualiza `.env`, envia lista de comandos |
| `cmd_ajuda` | `/ajuda` | Alias de `cmd_start` |
| `cmd_status` | `/status` | Mostra chat_id, último briefing, itens no histórico, próximo horário |
| `cmd_historico` | `/historico` | Lista episódios gerados hoje, com botões "play:" |
| `callback_play` | callback `play:` | Envia o mp3 do episódio (`send_audio`) |
| `callback_feedback` | callback `fb:` | Processa 👍/👎, chama `record_feedback`, remove o teclado |
| `cmd_aprendizado` | `/aprendizado` | `format_learning_status(load_adaptive_state())` |
| `cmd_analise` | `/analise` | Roda `run_weekly_analysis` sob demanda |
| `cmd_sincronia` | `/sincronia` | Força `sync_youtube_signals`, atualiza vetor e pesos |
| `cmd_config` | `/config` | Mostra quotas (`load_quotas()`) e `signal_weights` atuais |
| `weekly_analysis_job` | job semanal (dom 08:00) | Roda `run_weekly_analysis` e envia relatório via `send_text` |
| `cmd_perfil` | `/perfil [...]` | Visualiza/edita perfil (`add`/`rem`/`set` para interesse/ignorar/vip/score/cards) |
| `cmd_url` | `/url <link>` | Roda `main.py "url:<link>"`, envia até 3 itens |
| `cmd_generate` | comandos dinâmicos de `COMMANDS` | Handler genérico — ver abaixo |

Detalhes de uso e exemplos: [COMMANDS.md](COMMANDS.md).

### `cmd_generate(update, context, sources, label, cmd_key='')`
Handler genérico usado pelos comandos dinâmicos de `COMMANDS`:
1. Registra `chat_id` em `telegram_state.json`.
2. `record_command_usage(cmd_key)`.
3. Avisa o usuário ("⏳ Gerando ...").
4. `_run_main_py(sources)` + `_wait_and_collect(timeout=360)`.
5. Acrescenta vídeos do YouTube via `_fetch_youtube_for_cmd(cmd_key)`.
6. Se houver itens, avisa quantidade e chama `_send_items(bot, chat_id, items, cmd_key)`.

### `_build_feedback_keyboard(item) -> InlineKeyboardMarkup`
Monta o teclado inline com botões "👍 Relevante" / "👎 Não curto". O
`callback_data` segue o formato:

```
fb:<+1|-1>:<hash8>:<src_short>:<sid_short>:<score>
```

- `hash8` = `md5(f"{source_name}{title}")[:8]`
- `src_short` = `source_name` sem espaços, até 10 chars
- `sid_short` = `source_id[:8]`
- `score` = `int(item['_score'])` (0–10)

Payload típico tem ~36 bytes UTF-8 (limite do Telegram é 64 bytes).

### `_apply_quotas(items, cmd_key) -> list`
Aplica `max_por_fonte` e `max_total` de `load_quotas(cmd_key)` (seção
`telegram.quotas` do `config.yaml`). Se não houver quota configurada para o
comando, retorna os itens sem alteração.

### `_send_items(bot, chat_id, items, cmd_key='')`
Pipeline de envio usado por todos os comandos on-demand:
1. `enrich_item` em cada item (fallback: `score_item` + `_image_url=None` em
   caso de erro).
2. `deduplicate` + ordena por `_score` desc.
3. `load_profile()` + `filter_and_score_items` (bloqueio, score Gemini,
   tradução, recálculo adaptativo, filtro por `score_minimo_enviar`,
   `diversity_guard`).
4. `_apply_quotas(items, cmd_key)`.
5. Envia até `max_items_per_category * 3` itens via `send_item_card` com
   `_build_feedback_keyboard`.
6. Se algum item tiver `_audio_path` válido, oferece botão "🎵 Ouvir episódio
   completo" (`play:<folder>`).
7. Atualiza `sent_item_ids` em `telegram_state.json`.

### `send_morning_briefing(context)`
Job diário (07:00):
1. Se `adaptive_state['last_youtube_sync'] != hoje`, tenta sincronizar sinais
   do YouTube (`get_youtube_credentials` → `sync_youtube_signals` →
   atualiza `youtube_interest_vector`, `last_youtube_sync`,
   `signal_weights`).
2. `_run_main_py(BRIEFING_SOURCES)` + `send_briefing_header` (enquanto gera).
3. `_wait_and_collect(timeout=600)`.
4. Agrupa itens por `source_id`, envia `send_section_header` por seção e,
   para cada seção, `enrich_item` + `deduplicate` + ordena + envia até
   `max_items_per_category` itens com `_build_feedback_keyboard`.
5. Atualiza `last_briefing` e envia mensagem de encerramento.

### Helpers e `main()`
- `_set_env_chat_id(chat_id)` — grava/atualiza `TELEGRAM_CHAT_ID` no `.env`.
- `_make_command_handler(sources, label, cmd_key)` — factory de
  `CommandHandler` para os comandos dinâmicos.
- `main()` — valida `BOT_TOKEN`, registra todos os handlers (estáticos +
  dinâmicos de `COMMANDS`), `CallbackQueryHandler` para `^play:` e `^fb:`, e
  agenda `send_morning_briefing` (diário, 07:00) e `weekly_analysis_job`
  (semanal, domingo 08:00) via `JobQueue`.

---

## `src/content_enricher.py`

Enriquecimento de itens: imagem, score, deduplicação, diversidade e tradução.

### Constantes
- `CACHE_DIR = output/_telegram_cache`, `IMG_CACHE_DIR`, `TRANS_CACHE_FILE`.
- `USER_KEYWORDS` — lista de termos do perfil do Rafael (Grêmio, catolicismo,
  IA, conservadorismo, agronegócio, Paraná, Copa, filosofia, Europa, etc.)
  usados em `score_item`.
- `TRUSTED_SOURCES` — fontes que ganham bônus de score (Vatican News, Padre
  Paulo Ricardo, Mises, Gazeta do Povo, Jovem Pan, Grêmio, ESPN, GE, GauchaZH,
  WSJ, etc.).
- `TOPIC_KEYWORDS` — dict de tópicos → palavras-chave para `diversity_guard`:
  `copa`, `gremio`, `ia`, `papa`, `politica_br`, `economia`.

### Funções

**1. Extração de imagem**
- `extract_image(url, item) -> str | None` — cache em `IMG_CACHE_DIR`
  (chave = md5 da URL). Para URLs do YouTube extrai a thumbnail
  (`maxresdefault.jpg`); caso contrário tenta `og:image` via
  `requests` + `BeautifulSoup`; fallback `_extract_from_item`.
- `_extract_from_item(item)` — usa `item['image']` ou thumbnail do YouTube se
  `source_type == 'youtube'`.
- `_save_img_cache(path, value)`.

**2. Score de relevância**
- `score_item(item) -> int` (0–10) — soma:
  - até 5 pontos por matches em `USER_KEYWORDS` (`2 * matches`, capado em 5)
  - +2 se `source_name` está em `TRUSTED_SOURCES`
  - +2 se publicado hoje, +1 se ontem (com base em `published_at`)
  - +1 se tem imagem/url, +1 se tem `url`
  - resultado capado em 10.

**3. Deduplicação**
- `_normalize_title(title)` — lowercase, remove pontuação e stopwords PT,
  mantém as 8 primeiras palavras.
- `deduplicate(items) -> list` — garante `_score` em todos os itens
  (`score_item` se ausente); remove duplicatas por URL idêntica (mantém o de
  maior `_score`); depois remove por similaridade de título normalizado
  (`difflib.SequenceMatcher.ratio() >= 0.55`), mantendo o de maior score.

**3b. Diversidade de tópicos**
- `_detect_topic(item) -> str | None` — verifica `title` + `source_name`
  contra `TOPIC_KEYWORDS`, retorna o primeiro tópico que casar (ou `None`).
- `diversity_guard(items, max_per_topic=2) -> list` — percorre a lista (já
  ordenada por score) e descarta itens além de `max_per_topic` por tópico
  detectado; itens sem tópico passam sem limite.

**4. Tradução EN→PT**
- `_load_trans_cache()` / `_save_trans_cache(cache)` — cache JSON em
  `TRANS_CACHE_FILE`, chave = `md5(title)`.
- `_is_english(text) -> bool` — heurística: `>=4` palavras comuns em inglês
  (`the, and, for, ...`) encontradas via regex `\b[a-z]{2,}\b`.
- `_gemini_call_with_retry(prompt, model, max_tokens) -> str` — wrapper
  `@retry(stop_after_attempt(3), wait_exponential(min=2, max=8), reraise=False)`
  sobre `litellm.completion(timeout=15)`. **Reutilizado por
  `profile_filter.py` e `adaptive_engine.py`.**
- `translate_if_needed(title, text) -> (title, text)` — se `_is_english`,
  consulta cache; se não tiver, chama Gemini (`TELEGRAM_LLM_MODEL` ou
  `gemini/gemini-2.5-flash-lite`) pedindo JSON `{"title":..., "text":...}` e
  cacheia o resultado. Em caso de erro, retorna o original.

**5. Enrich completo**
- `enrich_item(item) -> dict` — aplica `translate_if_needed`,
  `extract_image`, `score_item`; retorna cópia do item com `title`, `text`,
  `_image_url`, `_score` atualizados.

---

## `src/profile_filter.py`

Perfil de interesses do usuário e pipeline de filtragem/score.

### Constantes
- `MODEL_FILTER = os.getenv('TELEGRAM_LLM_MODEL', 'gemini/gemini-2.5-flash-lite')`

### Perfil (`telegram.perfil` em `config.yaml`)
- `load_profile() -> dict` — lê `telegram.perfil`; se ausente/erro, retorna
  `_default_profile()`. Sempre passa por `_validate_profile` (completa chaves
  faltantes com o default).
- `_default_profile()` — perfil padrão do Rafael: `nome: Rafael`,
  `interesses_primarios` (5 itens), `fontes_vip` (4 fontes), `ignorar_sempre`
  (5 categorias), `idioma_preferido: pt-BR`, `score_minimo_enviar: 5`,
  `max_cards_por_comando: 8`.
- `_validate_profile(perfil)` — preenche chaves ausentes com os defaults.
- `save_profile(profile)` — grava `telegram.perfil` de volta em
  `config.yaml` via `yaml.safe_load`/`yaml.dump(allow_unicode=True,
  default_flow_style=False, sort_keys=False)`, preservando o restante do
  arquivo.

### Filtragem
- `should_block(item, profile) -> bool` — verifica se `title`+`source_name`
  contém alguma palavra de `ignorar_sempre`.
- `score_batch_with_gemini(items, profile) -> list` — pontua até 5 itens por
  chamada Gemini (`MODEL_FILTER`). Prompt inclui `interesses_primarios` e
  `fontes_vip` (bônus +2). Espera JSON
  `[{"i":1,"score":8,"motivo":"..."}]`; em caso de erro/falta, `_score=5`,
  `_motivo='fallback'`.
- `filter_and_score_items(items, profile) -> list` — pipeline de 7 passos:
  1. `should_block` remove itens indesejados.
  2. `score_batch_with_gemini` em lotes de 5 (`BATCH_SIZE=5`).
  3. Se `idioma_preferido == 'pt-BR'` e `_is_english`, traduz via
     `translate_if_needed`.
  4. Recalcula `_score` com `adaptive_engine.compute_adaptive_score`
     (carrega `adaptive_state`, usa o score do Gemini como `gemini_score`,
     atualiza `update_source_reputation` por `source_name`, salva o estado
     uma única vez ao final). Erros são logados em `debug` e ignorados.
  5. Filtra por `score_minimo_enviar`.
  6. Ordena por `_score` desc.
  7. `diversity_guard(filtered_by_score, max_per_topic=2)`.

### Formatação
- `format_profile(profile) -> str` — HTML para `/perfil` (interesses, VIPs,
  ignorados, score mínimo, máx. cards, idioma).
- `format_help() -> str` — HTML para `/perfil ajuda` (sintaxe de
  add/rem/set).

---

## `src/telegram_sender.py`

Formatação e envio de mensagens para o Telegram.

### Constantes
- `MSG_DELAY = 1.0` (segundos entre mensagens, para respeitar rate limits).
- `SOURCE_EMOJIS` — emoji por `source_id` (ex: `catolicismo: '✝️'`,
  `tecnologia: '💻'`, `gremio: '⚽'`, `youtube: '▶️'`, etc.) — 23 entradas.
- `CATEGORY_TITLES` — título de seção em português por `source_id` (ex:
  `catolicismo: '✝️ Fé e Reflexão'`, `tecnologia: '💻 Tecnologia'`) — mesmas
  23 chaves.

### Formatação
- `_escape_html(text)` — escapa `&`, `<`, `>`.
- `_stars(score)` — `'⭐⭐'` se `score>=8`, `'⭐'` se `score>=5`, senão `''`.
- `_extract_bullets(text, max_bullets=3)` — usa linhas já formatadas como
  bullet (`•`, `-`, `*`, `–`) se existirem; senão divide o texto em frases
  (regex `(?<=[.!?])\s+`) e usa as primeiras `max_bullets` com mais de 20
  caracteres (truncadas em 120).
- `_source_tags(source_id, source_name)` — gera até 3 hashtags
  (`#catolicismo`, `#conservadorismo`, `#futebol`, `#tecnologia`, `#noticias`,
  `#agro`) com base em substrings do `source_id`.
- `format_item_html(item, enriched) -> str` — monta o card: cabeçalho
  (emoji + nome da fonte + estrelas), título (linkado se houver `url`),
  bullets, link ("Ler artigo completo" ou "Assistir no YouTube" se
  `source_type == 'youtube'`), hashtags.

### Envio
- `send_item_card(bot, chat_id, item, enriched, reply_markup=None)` — envia
  `send_photo` (com `_image_url`) ou `send_message` como fallback se a foto
  falhar; aceita `reply_markup` (usado para os botões de feedback).
- `send_audio(bot, chat_id, mp3_path, caption)` — envia o mp3 (caption
  truncada em 1024 chars).
- `send_section_header(bot, chat_id, source_id)` — envia separador
  `━ × 20` + `CATEGORY_TITLES[source_id]`.
- `send_briefing_header(bot, chat_id, weather_text='', finance_text='', verse='')`
  — cabeçalho do briefing matinal ("☀️ Bom dia, Rafael!" + data em PT-BR +
  clima/finanças/versículo opcionais).
- `send_text(bot, chat_id, text, parse_mode='HTML', disable_preview=True)` —
  envio de texto simples (usado por `/analise`, `weekly_analysis_job`, etc.).

---

## `src/adaptive_engine.py`

Motor de aprendizado adaptativo — documentação detalhada em
[ADAPTIVE_SYSTEM.md](ADAPTIVE_SYSTEM.md) e
[ai-context/STATE_SCHEMA.md](ai-context/STATE_SCHEMA.md). Resumo das
funções em [ai-context/FUNCTIONS_INDEX.md](ai-context/FUNCTIONS_INDEX.md).

---

## `src/sources/youtube.py`

Plugin de coleta de vídeos do YouTube (usado pela fonte `youtube` em
`config.yaml` e pela busca por keyword do bot).

- `MAX_TRANSCRIPT_CHARS = 600`, `_transcript_api = YouTubeTranscriptApi()`.
- `_build_client(api_key, credentials=None)` — usa OAuth `credentials` se
  fornecido, senão `developerKey=api_key`.
- `_get_uploads_playlist_id(youtube, channel_id)` — playlist de uploads do
  canal.
- `_get_recent_videos(youtube, playlist_id, max_results, days_lookback)` —
  vídeos recentes (filtra "Private video"/"Deleted video" e por
  `days_lookback`).
- `_enrich_with_stats(youtube, videos)` — adiciona `views` e `description`
  (até 400 chars).
- `_get_top_comments(api_key, video_id, max_comments=5)` — sempre via API key
  (OAuth `youtube.readonly` não permite `commentThreads`); filtra comentários
  até 220 chars sem links, ordena por likes, retorna top 3.
- `_try_get_transcript(video_id, lang_pref)` — tenta `lang_pref`, depois
  qualquer idioma; retorna até `MAX_TRANSCRIPT_CHARS`.
- `_fetch_from_channels(youtube, api_key, channels, max_per_channel, days_lookback, max_total, lang_pref)`
  — amostra canais aleatoriamente, coleta vídeos recentes, enriquece com
  stats/transcript/comentários.
- `get_subscription_channels(youtube, max_channels=50)` — lista canais
  inscritos (via OAuth, paginado).
- `fetch(source_config, credentials=None) -> list[dict]` — entrada principal:
  combina vídeos das inscrições (`subscriptions_ratio` do `settings`, só se
  `credentials` presente) com vídeos dos canais configurados
  (`source_config['channels']`), respeitando `max_videos_total`.
- `search_youtube_by_keyword(query, youtube_service, max_results=3, published_after_hours=48) -> list`
  — busca (`search().list`, `relevanceLanguage='pt'`, `regionCode='BR'`,
  `order='relevance'`) vídeos publicados nas últimas `published_after_hours`
  horas; retorna itens no formato padrão (`source_id='youtube'`,
  `source_type='youtube'`). Usado por `telegram_bot._fetch_youtube_for_cmd`.

---

## `src/auth.py`

OAuth do YouTube (escopo `youtube.readonly`).

- `SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']`
- `get_youtube_credentials() -> Credentials | None`:
  - Retorna `None` se `credentials.json` não existir.
  - Reaproveita `token.json` se válido; renova via `refresh_token` se
    expirado; caso contrário inicia `InstalledAppFlow.run_local_server`
    (fluxo interativo — requer navegador na primeira execução).
  - Persiste o token atualizado em `token.json`.

---

## `plugins/`

Cada plugin exporta `fetch(source_config, credentials=None) -> list[dict]` e
é carregado dinamicamente por `main.py` (`_load_plugins`) se o arquivo não
começar com `_` e tiver `fetch`.

| Plugin | `type` em config.yaml | Resumo |
|---|---|---|
| `biblia.py` | `biblia` | Passagens via ABíbliaDigital (`abibliadigital.com.br`). Settings: `token_env`, `version` (nvi/acf/ra/kjv/bbe/apee/rvr), `mode` (random/book/passage), `book`, `passage`, `max_items`. |
| `gdelt.py` | `gdelt` | Notícias do GDELT (sem auth), com `QUERIES` focadas no perfil (política conservadora, agronegócio Paraná, catolicismo, IA/tecnologia). Retorna `source_id='gdelt'`, `source_type='rss'`. |
| `efemerides.py` | `efemerides` | "Hoje na História" via API `pt.wikipedia.org/api/rest_v1/feed/onthisday`. `CATEGORY_LABELS`: selected, events, births, deaths. Settings: `max_events`, `categories`. |
| `filmes.py` | `filmes` | TMDB (`TMDB_BASE`). `MODES`: trending, now_playing, upcoming, top_rated (com `MODE_LABEL` em PT). Settings: `api_key_env`, `mode`, `language`, `region`, `max_movies`. |
| `trivia.py` | `trivia` | Perguntas via OpenTDB (`opentdb.com/api.php`). `DIFFICULTY_PT` traduz easy/medium/hard. Settings: `amount`, `category`, `difficulty`. |
| `receitas.py` | `receitas` | Receita do dia via TheMealDB (random/filter/lookup) + feeds RSS (Panelaterapia, Na Minha Panela). `AREA_PT`/`CATEGORY_PT` traduzem áreas/categorias. Limites: `MAX_RECIPE_CHARS=3000`, `MAX_RSS_CANDIDATES=15`, `MAX_RSS_FETCH_TRIES=5`. |
| `concursos_pci.py` | `concursos_pci` | Notícias de concursos via scraping do PCI Concursos (trafilatura). Settings: `max_items`, `days_lookback`. |
| `reddit.py` | `reddit` | Tendências de subreddits via RSS (`reddit.com/r/<sub>/top/.rss?t=<timeframe>`), com `_clean_summary` limpando HTML/"submitted by"/links. Settings: `max_per_subreddit`, `max_total`, `timeframe`, `min_score`. **Sem comando dedicado no bot** (removido), mas a fonte continua em `config.yaml`. |
| `horoscopo.py` | — | Horóscopo por pares de signos (`SIGN_PAIRS`), via feeds + trafilatura, `SIGN_PT` para tradução. `MAX_CHARS=800`. Não está referenciado em `config.yaml: sources:` atualmente. |
| `url.py` | `url` (CLI `url:<link>`) | Extrai conteúdo de uma URL via `trafilatura`; se for YouTube (`_YT_DOMAINS`/`_YT_ID_RE`), usa `_fetch_youtube` (transcript). `MAX_CONTENT_CHARS_DEFAULT=3000`. Usado por `/url` do bot. |
| `podcast.py` | `podcast` (CLI `podcast:<url>` ou `podcast:url=...,start=...,duration=...,topic=...`) | Transcreve/resume episódios de podcast (RSS, URL direta ou YouTube) via Whisper. Settings: `url`, `max_items` (1), `days_lookback` (7), `show_notes_min_chars` (500), `whisper_start` (0), `whisper_duration` (600), `topic`, `whisper_model` (base). Dependências opcionais: `openai-whisper`, `yt-dlp`. |
| `clipping.py` | `clipping` (CLI `clipping:<tema>`) | "O que a imprensa diz sobre X" — busca cobertura de um tema em múltiplos veículos via feeds + trafilatura. Settings: `max_sources` (5), `days_lookback` (1), `fetch_content`, `max_content_chars` (2000). |
| `whatsapp.py` | `whatsapp` | Lê exportações `.zip` de conversas do WhatsApp (formatos Android/iOS PT-BR) e resume mensagens do período. Settings: `path`, `days_lookback` (1), `max_messages` (150), `ignore_media` (true). |
| `exemplo_plugin.py` | `exemplo_plugin` | Template/exemplo mínimo ("Frase do Dia") demonstrando o contrato `fetch()`. Settings: `categoria` (motivacional/filosofia/humor). Não usado em produção. |

> Nota: `reddit` (fonte) e `reddit.py` (plugin) continuam presentes no
> projeto, mas o comando `/reddit` foi removido do `telegram_bot.py`, assim
> como `/cultura`.
