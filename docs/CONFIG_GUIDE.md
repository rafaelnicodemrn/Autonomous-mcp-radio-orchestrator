# Guia de Configuração — `config.yaml`

`config.yaml` é a configuração central do projeto. É lido por `main.py`
(geração de episódios), `scheduler.py` (agendamento) e
`telegram_bot.py`/`src/profile_filter.py` (perfil, quotas). Edições feitas
via `/perfil` (bot) são gravadas de volta neste arquivo, preservando o
restante via `yaml.safe_load`/`yaml.dump(allow_unicode=True,
default_flow_style=False, sort_keys=False)`.

## Seções de topo

### `radio:`
```yaml
radio:
  name: "RadioIA Pessoal"
  background_music: ""
  background_volume_db: -22
```
Nome da "rádio" e configuração de música de fundo (vazio = desabilitada) e
seu volume em dB.

### `llm:`
```yaml
llm:
  model: "gemini/gemini-3.1-flash-lite"
```
Modelo padrão de **geração** de roteiro usado por `main.py` /
`src/script_generator.py`. Equivale à constante `MODEL_GENERATE` em
`telegram_bot.py`. O modelo de **filtragem** (`gemini/gemini-2.5-flash-lite`)
é controlado separadamente via env `TELEGRAM_LLM_MODEL` (default no código,
não em `config.yaml`).

### `tts:`
```yaml
tts:
  provider: google
  google:
    credentials_env: GOOGLE_APPLICATION_CREDENTIALS
    language_code: pt-BR
    voice_map:
      pt-BR-ThalitaMultilingualNeural: pt-BR-Chirp3-HD-Aoede
      pt-BR-AntonioNeural:             pt-BR-Chirp3-HD-Charon
      pt-BR-FranciscaNeural:           pt-BR-Chirp3-HD-Kore
```
Provider de TTS. `google` usa Google Cloud TTS Chirp3-HD (cota gratuita de
1M chars/mês), com `voice_map` traduzindo as vozes "lógicas" (edge-tts) para
as vozes Chirp3-HD equivalentes. Para usar o fallback edge-tts (sem
credenciais), troque por:
```yaml
tts:
  provider: edge_tts
```

### `narrators:`
```yaml
narrators:
  - name: "Ana"
    voice: "pt-BR-ThalitaMultilingualNeural"
    personality: "descontraída, curiosa e bem-humorada — faz perguntas e reage com naturalidade"
  - name: "Carlos"
    voice: "pt-BR-AntonioNeural"
    personality: "analítico e direto — complementa com contexto e opinião assertiva"
```
Os dois narradores usados nos roteiros gerados (diálogo).

### `vinheta:`
```yaml
vinheta:
  voice: "pt-BR-FranciscaNeural"
  rate: "+15%"
```
Voz e velocidade usadas para vinhetas/aberturas geradas por
`src/vinheta.py`.

### `announcements:`
```yaml
announcements:
  enabled: true
```
Habilita anúncios/spots no episódio.

### `spots:` e `spots_config:`
```yaml
spots:
  - id: reflexao-crista
    type: llm
    topic: "Uma reflexão cristã católica breve e inspiradora para o dia, citando um santo ou passagem bíblica"
    duration_seconds: 30
    max_per_day: 2

spots_config:
  fallback_every: 0
  between_episodes_every: 0
```
`spots` define anúncios gerados por LLM (aqui, uma reflexão católica diária,
até 30s, máx. 2/dia). `spots_config` controla a frequência de inserção
(`0` = desabilitado nos modos `fallback`/`between_episodes`).

## `sources:` — fontes de conteúdo

Lista de 28 fontes. Cada entrada tem `id`, `type`, `name`, `enabled`,
opcionalmente `model` (sobrescreve `llm.model` para esta fonte — todas
atualmente usam `gemini/gemini-3.1-flash-lite`) e `settings:` específico do
`type`.

### Exemplo completo — `youtube`
```yaml
- id: youtube
  type: youtube
  name: "Vídeos do YouTube"
  enabled: true
  model: "gemini/gemini-3.1-flash-lite"
  channels:
    - id: UCaGmdJSSiR7fkh2A-c6emsA
      name: "G1"
    # ... 19 canais no total
  settings:
    max_videos_per_channel: 1
    max_videos_total: 8
    days_lookback: 3
    language_preference: [pt, en]
    subscriptions_ratio: 0.4   # ativar após OAuth
```
- `channels` — lista de 19 canais (G1, Jovem Pan News, CNN Brasil, Band
  Jornalismo, CazeTV, Brasil Paralelo, Bernardo Küster, TinoCanDoTV,
  Sobrevivencialismo, Padre Paulo Ricardo, Vatican News PT, Santo Flow, Flow
  Podcast, Inteligência Ltda, Manual do Mundo, Nerdologia, Ciência Todo Dia,
  GE TV, ESPN Brasil, Primo Rico).
- `subscriptions_ratio: 0.4` — 40% dos `max_videos_total` vêm das inscrições
  do usuário (via OAuth), o restante dos canais configurados.

### Fontes RSS — exemplo (`noticias`)
```yaml
- id: noticias
  type: rss
  name: "Notícias do Dia"
  enabled: true
  model: "gemini/gemini-3.1-flash-lite"
  feeds:
    - url: "https://g1.globo.com/rss/g1/"
      name: "G1"
    - url: "https://www.gazetadopovo.com.br/feed/rss/ultimas-noticias.xml"
      name: "Gazeta do Povo"
    # Agência Brasil, CNN Brasil, Jovem Pan, Revista Oeste
  settings:
    max_items_per_feed: 1
    max_items_total: 4
    days_lookback: 1
```
`settings.max_items_per_feed` limita quantos itens vêm de cada feed,
`max_items_total` limita o total da fonte, `days_lookback` filtra itens
publicados nos últimos N dias.

### Tabela de fontes

| `id` | `type` | Nome | Resumo de `settings` |
|---|---|---|---|
| `youtube` | youtube | Vídeos do YouTube | 19 canais; `max_videos_total: 8`, `days_lookback: 3`, `subscriptions_ratio: 0.4` |
| `noticias` | rss | Notícias do Dia | 6 feeds (G1, Gazeta do Povo, Agência Brasil, CNN Brasil, Jovem Pan, Revista Oeste); `max_items_total: 4`, `days_lookback: 1` |
| `gdelt` | gdelt | GDELT Brasil | `max_items_total: 4`, `days_lookback: 1` (sem auth, queries fixas no plugin) |
| `noticias-internacionais` | rss | Notícias Internacionais | WSJ, Fox News, NY Post, The Economist; `max_items_total: 3`, `days_lookback: 1` |
| `noticias-locais` | rss | Notícias Locais | G1 Paraná, Guia Medianeira, Google News Medianeira; `max_items_total: 3`, `days_lookback: 1` |
| `catolicismo` | rss | Fé e Reflexão | Vatican News PT, Padre Paulo Ricardo, Canção Nova, Liturgia Diária, ACI Digital, TFP; `max_items_total: 3`, `days_lookback: 2` |
| `conservadorismo` | rss | Filosofia e Conservadorismo | Burke Instituto, Mises Brasil, Mises Institute, Brasil Paralelo; `max_items_total: 3`, `days_lookback: 7` |
| `biblia` | biblia | Palavra do Dia | `token_env: ABIBLIADIGITAL_TOKEN`, `version: nvi`, `mode: random`, `max_items: 1` |
| `politica` | rss | Política | Gazeta do Povo-Política, Veja-Política, Google Política; `max_items_total: 3`, `days_lookback: 1` |
| `agronegocio` | rss | Agronegócio | Canal Rural, Notícias Agrícolas; `max_items_total: 2`, `days_lookback: 2` |
| `tecnologia` | rss | Tecnologia | TecMundo, Techtudo, Olhar Digital, Canaltech, TabNews; `max_items_total: 4`, `days_lookback: 1` |
| `tecnologia-internacional` | rss | Tech Internacional | Ars Technica, The Verge, Wired, TechCrunch; `max_items_total: 3`, `days_lookback: 1` |
| `inteligencia-artificial` | rss | Inteligência Artificial | Anthropic, OpenAI, Google AI, Google IA PT; `max_items_total: 3`, `days_lookback: 1` |
| `gremio` | rss | Grêmio FBPA | Grêmio Oficial, GaúchaZH-Grêmio, GE Globo Esporte, Google Grêmio; `max_items_per_feed: 2`, `max_items_total: 6`, `days_lookback: 2` |
| `copa` | utility | Copa do Mundo 2026 | `football: {enabled: true, competition: WC, api_key_env: FOOTBALL_DATA_API_KEY}`; clima/finanças/loteria desabilitados |
| `brasileirao` | utility | Brasileirão | `football: {competition: BSA}` |
| `libertadores` | utility | Copa Libertadores | `football: {competition: CLI}` |
| `utilidades` | utility | Resumo do Dia | `weather` (Medianeira/Cascavel/Curitiba, `OPENWEATHER_API_KEY`, `forecast_days: 3`), `finance` (USD-BRL, EUR-BRL, BTC-USD), `lottery: false`, `sun` (lat/lng Medianeira, `tzid: America/Sao_Paulo`) |
| `efemerides` | efemerides | Hoje na História | `max_events: 3`, `categories: [selected, events]` |
| `quiz` | trivia | Quiz do Dia | `amount: 3` |
| `receitas` | receitas | Receita do Dia | feeds (Panelaterapia, Na Minha Panela), `areas: [Italian, Portuguese, Mexican]` |
| `filmes` | filmes | Cine Indica | `api_key_env: TMDB_API_KEY`, `mode: trending`, `language: pt-BR`, `region: BR`, `max_movies: 4` |
| `filmes-cartaz` | filmes | Filmes em Cartaz | `mode: now_playing`, `max_movies: 3` |
| `reddit` | reddit | Tendências do Reddit | subreddits: brasil, brdev, investimentos, futebol, ciencia, technology; `max_per_subreddit: 2`, `max_total: 6`, `timeframe: day`, `min_score: 50` |
| `europa` | rss | Europa e Viagens | Google News (Portugal/França/Itália/Luxemburgo); `max_items_per_feed: 2`, `max_items_total: 3`, `days_lookback: 3` |
| `concursos` | concursos_pci | Concursos Públicos | `max_items: 2`, `days_lookback: 2` |
| `musica-trabalho` | music | Música para Trabalhar | `source: jamendo`, `tags: classical`, `min_duration: 120`, `max_duration: 600`, `num_tracks: 3` |
| `musica-noite` | music | Playlist Gaúcha e Sertaneja | **`enabled: false`** — `source: local`, `num_tracks: 4` (arquivos em `music/gaucho/`, `music/sertanejo/`, `music/mpb/`) |

> A fonte `reddit` está habilitada em `config.yaml`, mas não há comando
> `/reddit` no bot (removido). Pode ser usada via
> `python main.py reddit`.

## `schedule:` — agendamento automático

```yaml
schedule:
  - time: "07:00"
    label: "Briefing Matinal"
    sources: [biblia, utilidades, catolicismo, noticias, tecnologia, politica, conservadorismo]
    days: [mon, tue, wed, thu, fri]

  - time: "08:00"
    label: "Briefing Fim de Semana"
    sources: [biblia, utilidades, catolicismo, noticias, conservadorismo, gremio]
    days: [sat, sun]

  # Eventos pontuais da Copa do Mundo 2026 (date + time, sources: [copa])
  - time: "11:00"
    date: "2026-06-11"
    label: "Abertura da Copa do Mundo 2026"
    sources: [copa]
  # + 2026-06-18, 2026-06-21, 2026-06-26 (jogos do Brasil), todos às 12:00
```

Consumido por `scheduler.py` (não pelo `telegram_bot.py`, que tem seu próprio
agendamento fixo para o briefing 07:00 e a análise semanal). Cada entrada
roda `main.py` com as `sources` indicadas no `time`/`days` (recorrente) ou
`date`/`time` (pontual). Comentário no `config.yaml` também documenta o uso
manual via CLI:

```bash
# Briefing completo
python main.py biblia utilidades catolicismo noticias tecnologia politica conservadorismo
# Fé e filosofia
python main.py biblia catolicismo conservadorismo
# Tech + IA
python main.py tecnologia inteligencia-artificial tecnologia-internacional
# Notícias
python main.py noticias politica noticias-internacionais
# Futebol / Grêmio
python main.py gremio copa brasileirao libertadores
# Filmes
python main.py filmes filmes-cartaz
# Local
python main.py noticias-locais agronegocio
# URL avulsa
python main.py "url:https://site.com/artigo"
```

## `telegram:` — perfil e quotas do bot

### `telegram.perfil`
```yaml
telegram:
  perfil:
    nome: Rafael
    interesses_primarios:
      - catolicismo tradicional
      - filosofia conservadora
      - tecnologia e inteligência artificial
      - política brasileira
      - política internacional
    fontes_vip:
      - Padre Paulo Ricardo
      - Vatican News
      - Brasil Paralelo
      - Gazeta do Povo
    ignorar_sempre:
      - esportes olímpicos
      - fofoca e celebridades
      - loteria
      - horóscopo
      - reality show
    idioma_preferido: pt-BR
    score_minimo_enviar: 5
    max_cards_por_comando: 8
```

| Campo | Tipo | Uso |
|---|---|---|
| `nome` | str | Exibido no perfil (`/perfil`) |
| `interesses_primarios` | list[str] | Enviado ao Gemini em `score_batch_with_gemini` para pontuar relevância |
| `fontes_vip` | list[str] | Fontes que recebem bônus de +2 no score do Gemini |
| `ignorar_sempre` | list[str] | Palavras/frases que, se presentes em `title`+`source_name`, bloqueiam o item (`should_block`) |
| `idioma_preferido` | str | Se `pt-BR`, ativa tradução automática EN→PT (`translate_if_needed`) |
| `score_minimo_enviar` | int (0-10) | Filtro final em `filter_and_score_items` — itens com `_score` abaixo não são enviados |
| `max_cards_por_comando` | int (1-20) | Exibido no perfil; o limite efetivo de envio é `max_items_per_category` (em `telegram_state.json`) × 3, combinado com `telegram.quotas` |

Editável via comando `/perfil` (ver [COMMANDS.md](COMMANDS.md)).

### `telegram.quotas`
```yaml
quotas:
  briefing:
    max_por_fonte: 3
    max_total: 15
  tech:
    max_por_fonte: 3
    max_total: 8
  fe:
    max_por_fonte: 3
    max_total: 8
  gremio:
    max_por_fonte: 3
    max_total: 8
  noticias:
    max_por_fonte: 3
    max_total: 8
  filmes:
    max_por_fonte: 3
    max_total: 8
  local:
    max_por_fonte: 3
    max_total: 8
```

Lido por `load_quotas(cmd_key)` em `telegram_bot.py` e aplicado por
`_apply_quotas`. A chave é o nome do comando **sem a barra** (`briefing`,
`tech`, `fe`, etc.). Comandos sem entrada aqui (ex: `/youtube`) não têm
quota extra — apenas o limite geral de `max_items_per_category` (×3) do
`_send_items`. Visualizável via `/config`.

## Variáveis de ambiente (`.env`)

Definidas em `.env.example` (copiar para `.env`):

| Variável | Uso |
|---|---|
| `ANTHROPIC_API_KEY` | Obrigatória — usada por componentes que chamam a API Anthropic |
| `YOUTUBE_API_KEY` | Obrigatória — API key do YouTube Data API v3 (busca, comentários, fonte `youtube` sem OAuth) |
| `OPENWEATHER_API_KEY` | Clima (`utilidades`) — openweathermap.org |
| `JAMENDO_CLIENT_ID` | Música (`musica-trabalho`) — developer.jamendo.com |
| `FOOTBALL_DATA_API_KEY` | Futebol (`copa`, `brasileirao`, `libertadores`) — football-data.org |
| `TMDB_API_KEY` | Filmes (`filmes`, `filmes-cartaz`) — themoviedb.org |
| `ABIBLIADIGITAL_TOKEN` | Bíblia (`biblia`) — abibliadigital.com.br |
| `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` | Providers TTS alternativos (opcional) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho do JSON de credenciais do Google Cloud TTS (`tts.provider: google`) |
| `TELEGRAM_BOT_TOKEN` | Token do bot Telegram (não está em `.env.example`, mas é obrigatório para `telegram_bot.py`) |
| `TELEGRAM_CHAT_ID` | Chat de destino do briefing/comandos — definido automaticamente por `/start` |
| `TELEGRAM_LLM_MODEL` | Sobrescreve `MODEL_FILTER` (`gemini/gemini-2.5-flash-lite`) usado em `profile_filter.py`, `content_enricher.py` e `adaptive_engine.py` |
