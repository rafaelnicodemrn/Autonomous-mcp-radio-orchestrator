# RadioIA 📻

Rádio personalizada gerada por inteligência artificial. O sistema coleta conteúdo de diversas fontes (YouTube, RSS, Reddit, APIs públicas), gera roteiros com Claude e produz episódios em MP3 narrados por vozes sintéticas — tudo automaticamente.

---

## Como funciona

```
Fontes → Conteúdo → Claude (roteiro) → TTS (áudio) → Episódio MP3
```

1. O `main.py` busca conteúdo das fontes configuradas
2. Claude gera um roteiro de rádio com os narradores configurados
3. Edge TTS (Microsoft) converte o roteiro em áudio
4. Os arquivos MP3 são salvos em `output/` organizados por data
5. O player web (`serve.py`) exibe e reproduz os episódios automaticamente

---

## Pré-requisitos

- Python 3.11+
- ffmpeg instalado e no PATH ([download](https://ffmpeg.org/download.html))
- Conta na [Anthropic](https://console.anthropic.com) (Claude)
- Conta no [Google Cloud](https://console.developers.google.com) (YouTube Data API v3)

---

## Instalação

```bash
# Clone o repositório
git clone https://github.com/fabianoallex/radioIA.git
cd radioIA

# Instale as dependências
pip install -r requirements.txt
```

> **Atualizando de uma versão anterior?** O `litellm` foi adicionado como dependência para suporte a múltiplos provedores de LLM. Se você já tinha o projeto instalado, rode `pip install -r requirements.txt` novamente para incluí-lo — ele é necessário mesmo usando apenas o Claude.

---

## Configuração

### 1. Variáveis de ambiente (`.env`)

Crie o arquivo `.env` na raiz do projeto:

```env
# Obrigatórias
ANTHROPIC_API_KEY=sk-ant-...
YOUTUBE_API_KEY=AIza...

# Opcionais (conforme os módulos habilitados)
OPENWEATHER_API_KEY=...        # Clima e previsão do tempo
JAMENDO_CLIENT_ID=...          # Músicas do Jamendo
FOOTBALL_DATA_API_KEY=...      # Futebol (football-data.org)
```

**Como obter cada chave:**

| Chave | Onde obter | Custo |
|-------|-----------|-------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Pago por uso |
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.developers.google.com) → YouTube Data API v3 | Gratuito (cota diária) |
| `OPENWEATHER_API_KEY` | [openweathermap.org](https://openweathermap.org/api) | Gratuito (1000 req/dia) |
| `JAMENDO_CLIENT_ID` | [developer.jamendo.com](https://developer.jamendo.com) | Gratuito |
| `FOOTBALL_DATA_API_KEY` | [football-data.org](https://www.football-data.org) | Gratuito (10 req/min) |
| `TMDB_API_KEY` | [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) | Gratuito |

---

### 2. Arquivo de configuração (`config.yaml`)

Toda a configuração da rádio está no `config.yaml`. Ele é dividido em:
- **`sources`** — fontes de conteúdo
- **`narrators`** — narradores e personalidades
- **`vinheta`** — vinheta da rádio
- **`radio`** — nome da rádio e configurações de mixagem
- **`llm`** — modelo de linguagem e provedor usado na geração de roteiros
- **`announcements`** — avisos de grade intercalados entre músicas no modo fallback
- **`spots`** — pool de spots (propagandas/comunicados) com rotação ponderada
- **`spots_config`** — frequência de injeção dos spots no fallback e entre episódios
- **`schedule`** — programação automática

---

## Fontes de conteúdo

### YouTube (`type: youtube`)

Busca vídeos recentes de canais configurados. Suporta OAuth para incluir inscrições.

```yaml
- id: youtube
  type: youtube
  name: "Vídeos do Youtube"
  enabled: true
  channels:
    - id: UCaGmdJSSiR7fkh2A-c6emsA
      name: "G1"
    - id: UC-wcdrzucnlKGBjyEUaEWaQ
      name: "Jovem Pan News"
  settings:
    max_videos_per_channel: 2    # máximo de vídeos por canal
    max_videos_total: 15         # total máximo
    days_lookback: 7             # busca vídeos dos últimos N dias
    language_preference: [pt, en]
    subscriptions_ratio: 0.6     # % de vídeos das inscrições (requer OAuth)
```

**Como ativar OAuth (inscrições do YouTube):**
1. No Google Cloud Console, crie credenciais OAuth 2.0 (Aplicativo Desktop)
2. Baixe o `client_secret.json` e coloque na raiz do projeto
3. Execute `python src/auth.py` uma vez para autenticar

---

### RSS (`type: rss`)

Lê feeds RSS de qualquer site. O Claude gera um boletim de notícias a partir dos artigos.

```yaml
- id: noticias
  type: rss
  name: "Notícias do Dia"
  enabled: true
  feeds:
    - url: "https://g1.globo.com/rss/g1/"
      name: "G1"
    - url: "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml"
      name: "Folha"
  settings:
    max_items_per_feed: 2    # itens por feed
    max_items_total: 12      # total máximo
    days_lookback: 1         # ignora itens mais antigos que N dias
```

**Feeds verificados e funcionando:**

| Veículo | URL |
|---------|-----|
| G1 | `https://g1.globo.com/rss/g1/` |
| Folha de São Paulo | `https://feeds.folha.uol.com.br/emcimadahora/rss091.xml` |
| Gazeta do Povo | `https://www.gazetadopovo.com.br/feed/rss/ultimas-noticias.xml` |
| Agência Brasil | `https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml` |
| CNN Brasil | `https://admin.cnnbrasil.com.br/rss` |
| Metrópoles | `https://www.metropoles.com/feed/` |
| Poder360 | `https://www.poder360.com.br/feed/` |
| TecMundo | `https://rss.tecmundo.com.br/feed` |
| Olhar Digital | `https://olhardigital.com.br/feed/` |
| Canaltech | `https://canaltech.com.br/rss/` |
| G1 São Paulo | `https://g1.globo.com/sao-paulo/rss/g1/sao-paulo.xml` |
| Google (cidade) | `https://news.google.com/rss/search?q=sua+cidade&hl=pt-BR&gl=BR` |

---

### Utilidades (`type: utility`)

Fonte especial para dados estruturados. Cada seção é opcional e independente.

```yaml
- id: utilidades
  type: utility
  name: "Resumo do Dia"
  enabled: true
  settings:

    weather:
      enabled: true
      cities:
        - "Sao Paulo,BR"
        - "Rio de Janeiro,BR"
      api_key_env: "OPENWEATHER_API_KEY"
      forecast_days: 3    # previsão dos próximos N dias (0 = desativado, máx 5)

    finance:
      enabled: true
      pairs:
        - "USD-BRL"    # Dólar
        - "EUR-BRL"    # Euro
        - "BTC-USD"    # Bitcoin

    lottery:
      enabled: true
      games:
        - megasena
        - lotofacil
        - quina
        # Outras: lotomania | timemania | duplasena | diadesorte

    football:
      enabled: true
      competition: WC              # código da competição
      api_key_env: FOOTBALL_DATA_API_KEY
```

**Códigos de competição disponíveis (football-data.org):**

| Código | Competição |
|--------|-----------|
| `WC` | FIFA World Cup |
| `BSA` | Campeonato Brasileiro Série A |
| `CL` | UEFA Champions League |
| `CLI` | Copa Libertadores |

O módulo narra automaticamente: resultados de ontem, jogos ao vivo (se houver) e agenda do dia.

---

### Reddit (`type: reddit`)

Busca os posts mais votados do dia em subreddits configurados.

```yaml
- id: reddit
  type: reddit
  name: "Tendências do Reddit"
  enabled: true
  subreddits:
    - brasil
    - investimentos
    - brdev
    - futebol
    - ciencia
  settings:
    max_per_subreddit: 3
    max_total: 10
    timeframe: day    # hour | day | week | month | year
    min_score: 50     # ignora posts com menos upvotes que isso
```

---

### Efemérides (`type: efemerides`)

Busca eventos históricos do dia na Wikipedia em português.

```yaml
- id: efemerides
  type: efemerides
  name: "Hoje na História"
  enabled: true
  settings:
    max_events: 3
    categories:
      - selected    # eventos curados pela Wikipedia (melhor qualidade)
      - events      # todos os eventos do dia
      # - births    # nascimentos notáveis
      # - deaths    # falecimentos notáveis
```

---

### Horóscopo (`type: horoscopo`)

Busca a previsão do dia para dois signos do zodíaco (Personare, com fallback Google News). Os 12 signos são cobertos em 6 duplas ao longo da programação, como nas rádios brasileiras.

```yaml
- id: horoscopo
  type: horoscopo
  name: "Horóscopo do Dia"
  enabled: true
  settings:
    # pair_index: 0   # omitir = rotação automática por dia do ano
```

**Duplas e índices:**

| Parâmetro | Signos |
|-----------|--------|
| `horoscopo:0` | Áries e Touro |
| `horoscopo:1` | Gêmeos e Câncer |
| `horoscopo:2` | Leão e Virgem |
| `horoscopo:3` | Libra e Escorpião |
| `horoscopo:4` | Sagitário e Capricórnio |
| `horoscopo:5` | Aquário e Peixes |

---

### Quiz (`type: trivia`)

Gera um segmento de quiz com perguntas da Open Trivia Database. O Claude apresenta as perguntas, lê as alternativas e revela as respostas com contexto.

```yaml
- id: quiz
  type: trivia
  name: "Quiz do Dia"
  enabled: true
  settings:
    amount: 5              # número de perguntas
    # category: 23        # categoria (ver tabela abaixo)
    # difficulty: medium  # easy | medium | hard (omitir = aleatório)
```

**Categorias disponíveis:**

| Código | Categoria |
|--------|-----------|
| 9 | Conhecimentos Gerais |
| 17 | Ciência e Natureza |
| 18 | Tecnologia |
| 21 | Esportes |
| 22 | Geografia |
| 23 | História |
| 25 | Arte |

---

### Filmes (`type: filmes`)

Busca filmes no [The Movie Database (TMDB)](https://www.themoviedb.org) e gera um quadro de indicações cinematográficas descontraído. Requer chave gratuita em **themoviedb.org/settings/api**.

```yaml
- id: filmes
  type: filmes
  name: "Cine Indica"
  enabled: true
  settings:
    api_key_env: TMDB_API_KEY
    mode: trending      # trending | now_playing | upcoming | top_rated
    language: pt-BR
    region: BR          # código ISO do país (filtra now_playing e upcoming)
    max_movies: 5       # quantidade de filmes no segmento
```

**Modos disponíveis:**

| Modo | Conteúdo |
|------|----------|
| `trending` | Filmes em tendência global hoje |
| `now_playing` | Em cartaz nos cinemas (filtra por `region`) |
| `upcoming` | Lançamentos futuros (filtra por `region`) |
| `top_rated` | Mais bem avaliados de todos os tempos |

**`.env`:**
```env
TMDB_API_KEY=sua_chave_aqui
```

---

### URL (`type: url`)

Gera um episódio a partir de qualquer URL — notícia, artigo, produto, curiosidade, piada, etc. O Claude identifica o tipo de conteúdo e adapta o tom automaticamente.

Não requer configuração no `config.yaml`. Use diretamente pelo CLI ou via MCP:

```bash
# CLI
python main.py "url:https://exemplo.com/artigo"

# Combinado com outras fontes
python main.py noticias "url:https://exemplo.com/artigo"
```

> **Nota:** URLs com `&` no PowerShell precisam de aspas duplas ao redor do argumento inteiro.

Sites que bloqueiam scrapers (alguns portais internacionais) podem não funcionar. A maioria dos portais brasileiros é compatível.

---

### Receitas (`type: receitas`)

Busca uma receita culinária e gera um quadro de rádio descontraído com apresentação dos ingredientes e modo de preparo.

Suporta dois modos:

**Sites brasileiros via RSS** (padrão quando `feeds` está configurado):

```yaml
- id: receitas
  type: receitas
  name: "Receita do Dia"
  enabled: true
  settings:
    feeds:
      - url: "https://www.panelaterapia.com/feed/"
        name: "Panelaterapia"
      - url: "https://www.naminhapanela.com/feed/"
        name: "Na Minha Panela"
```

**TheMealDB** (fallback automático se os feeds falharem, ou modo principal sem `feeds`):

```yaml
    areas:              # culinárias preferidas (TheMealDB)
      - Italian
      - Portuguese
      - Mexican
      - French
      - Japanese
```

As áreas disponíveis no TheMealDB incluem: `American`, `British`, `Chinese`, `French`, `Greek`, `Indian`, `Italian`, `Japanese`, `Malaysian`, `Mexican`, `Moroccan`, `Portuguese`, `Spanish`, `Thai`, `Turkish`, entre outras.

Se apenas `areas` for configurado (sem `feeds`), o TheMealDB é usado diretamente. Se ambos forem configurados, o RSS tem prioridade e o TheMealDB entra como fallback.

---

### Música (`type: music`)

Insere faixas musicais no episódio com vinheta de entrada e saída.

```yaml
# Jamendo (músicas licenciadas)
- id: musica
  type: music
  name: "Seleção Musical"
  enabled: false
  settings:
    num_tracks: 3
    source: "jamendo"
    jamendo:
      api_key_env: "JAMENDO_CLIENT_ID"
      tags: "lounge"    # lounge | jazz | ambient | pop | electronic | classical | rock
      min_duration: 60
      max_duration: 360

# Pasta local
- id: musica-local
  type: music
  name: "Playlist Local"
  enabled: false
  settings:
    num_tracks: 2
    source: "local"    # lê arquivos de música da pasta music/ e subpastas
```

---

## Narradores

Configure de 1 a 3 narradores. O Claude distribui as falas de acordo com as personalidades.

```yaml
narrators:
  - name: "Ana"
    voice: "pt-BR-ThalitaMultilingualNeural"
    personality: "descontraida, curiosa e bem-humorada"

  - name: "Carlos"
    voice: "pt-BR-AntonioNeural"
    personality: "analitico e direto"

  - name: "Julia"           # terceiro narrador (opcional)
    voice: "pt-BR-FranciscaNeural"
    personality: "irreverente e critica"
```

**Vozes pt-BR disponíveis (Edge TTS):**

| Voz | Gênero |
|-----|--------|
| `pt-BR-ThalitaMultilingualNeural` | Feminino |
| `pt-BR-AntonioNeural` | Masculino |
| `pt-BR-FranciscaNeural` | Feminino |

---

## Motor de voz (TTS)

O RadioIA suporta múltiplos provedores de síntese de voz. O padrão é **Edge TTS** (gratuito, sem chave de API). Para trocar, adicione a seção `tts:` ao `config.yaml`.

### Provedores disponíveis

| Provider | Qualidade | Custo | Pacote extra |
|----------|-----------|-------|--------------|
| `edge_tts` (padrão) | Boa | Gratuito | — |
| `openai` | Muito boa | Pago por caractere | `pip install openai` |
| `elevenlabs` | Excelente | Pago (tier gratuito limitado) | `pip install elevenlabs` |
| `google` | Muito boa | Pago (tier gratuito generoso) | `pip install google-cloud-texttospeech` |

### Configuração

```yaml
tts:
  provider: openai          # edge_tts | openai | elevenlabs | google
  openai:
    api_key_env: OPENAI_API_KEY
    model: tts-1-hd         # tts-1 (rápido) | tts-1-hd (maior qualidade)
```

### voice_map — troca de provider sem alterar narradores

Cada provider usa nomes de voz diferentes. O `voice_map` converte automaticamente os nomes configurados nos narradores para o equivalente no provider escolhido — sem precisar editar a seção `narrators`:

```yaml
tts:
  provider: openai
  openai:
    api_key_env: OPENAI_API_KEY
    model: tts-1-hd
    voice_map:
      pt-BR-ThalitaMultilingualNeural: nova    # feminino, natural
      pt-BR-AntonioNeural: onyx                # masculino, profundo
      pt-BR-FranciscaNeural: shimmer           # feminino, expressivo
```

Sem `voice_map`, o valor do campo `voice` de cada narrador é enviado diretamente ao provider — útil quando você já configurou os nomes do novo provider nos narradores.

### Referência de vozes por provider

**OpenAI** — vozes únicas (multilíngues): `alloy`, `ash`, `coral`, `echo`, `fable`, `onyx`, `nova`, `sage`, `shimmer`

**ElevenLabs** — use o `voice_id` da [Voice Library](https://elevenlabs.io/voice-library). Modelos: `eleven_multilingual_v2` (padrão), `eleven_turbo_v2_5`

**Google Cloud TTS** — vozes pt-BR recomendadas:

| Voz | Gênero | Qualidade |
|-----|--------|-----------|
| `pt-BR-Studio-B` | Masculino | Studio (melhor) |
| `pt-BR-Studio-C` | Feminino | Studio (melhor) |
| `pt-BR-Neural2-A` | Feminino | Neural2 |
| `pt-BR-Neural2-B` | Masculino | Neural2 |
| `pt-BR-Wavenet-A` | Feminino | WaveNet |

Exemplo completo para Google:

```yaml
tts:
  provider: google
  google:
    credentials_env: GOOGLE_APPLICATION_CREDENTIALS   # path do service account JSON
    language_code: pt-BR
    voice_map:
      pt-BR-ThalitaMultilingualNeural: pt-BR-Studio-C
      pt-BR-AntonioNeural: pt-BR-Studio-B
      pt-BR-FranciscaNeural: pt-BR-Neural2-A
```

> A vinheta (ID da rádio) usa o mesmo provider e também respeita o `voice_map`.

---

## Modelo de linguagem

O sistema usa [LiteLLM](https://github.com/BerriAI/litellm) para gerar roteiros, o que permite usar qualquer provedor de LLM sem alterar o código — basta configurar o `config.yaml` e adicionar a chave de API correspondente no `.env`.

### Padrão global

```yaml
llm:
  model: "claude-sonnet-4-6"   # padrão para todas as fontes
```

### Provedores suportados

| Provedor | Exemplo de model | Chave no `.env` |
|----------|-----------------|-----------------|
| **Anthropic** (padrão) | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini` | `OPENAI_API_KEY` |
| **Google Gemini** | `gemini/gemini-2.0-flash` | `GEMINI_API_KEY` |
| **Groq** (rápido e gratuito) | `groq/llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| **Ollama** (local, sem custo) | `ollama/llama3.2` | — |

Para Ollama, adicione também o endpoint:

```yaml
llm:
  model: "ollama/llama3.2"
  api_base: "http://localhost:11434"   # padrão do Ollama
```

### Override por fonte

Qualquer source pode usar um modelo diferente adicionando o campo `model`:

```yaml
- id: horoscopo
  type: horoscopo
  model: "claude-haiku-4-5-20251001"   # só nesta fonte; usa o llm.model nas demais
```

A resolução segue a ordem: **`model` da fonte → `llm.model` global → `claude-sonnet-4-6`**.

### Quando usar cada modelo (Anthropic)

| Modelo | Custo relativo | Quando usar |
|--------|---------------|-------------|
| `claude-haiku-4-5-20251001` | ~10× mais barato | Fontes com estrutura rígida: `horoscopo`, `trivia`, `receitas` |
| `claude-sonnet-4-6` | médio (padrão) | Fontes que exigem síntese e diálogo real: `youtube`, `rss`, `reddit`, `filmes` |
| `claude-opus-4-8` | ~5× mais caro | Qualidade máxima — produção corporativa ou fonte principal do dia |

> As fontes `horoscopo`, `trivia` e `receitas` já têm `model: "claude-haiku-4-5-20251001"` ativo no `config.yaml`.

> **Privacidade corporativa:** para conteúdos internos sensíveis, use Ollama com um modelo local — nenhum dado é enviado para APIs externas.

---

## Nome da rádio

Para personalizar o nome da rádio — seja para uso pessoal ou corporativo — basta alterar **uma única linha** no `config.yaml`:

```yaml
radio:
  name: "Rádio Empresa XYZ"   # ← só isso
```

Ao mudar esse campo, o nome se propaga automaticamente para:
- **Roteiros gerados pelo Claude** — a abertura do primeiro bloco do dia menciona "vocês estão na [Nome]"
- **Vinhetas** — `abertura`, `id` e `encerramento` gerados com o nome correto
- **Tags MP3** — campo `artist` de todos os episódios
- **Player web** — título da aba e cabeçalho da página
- **Scheduler** — mensagem de inicialização

---

## Vinheta

```yaml
vinheta:
  voice: "pt-BR-FranciscaNeural"
  rate: "+20%"    # velocidade da fala

  # Os textos são gerados automaticamente a partir de radio.name.
  # Descomente apenas se quiser um texto personalizado:
  # abertura: "Rádio Empresa XYZ — sua rádio personalizada!"
  # id: "Rádio Empresa XYZ!"
  # encerramento: "Rádio Empresa XYZ — até o próximo episódio!"
```

---

## Executando

### Gerar todos os episódios habilitados

```bash
python main.py
```

### Gerar uma fonte específica

```bash
python main.py noticias
python main.py copa
python main.py youtube noticias-locais    # múltiplas fontes
```

### Gerar episódio a partir de uma URL

```bash
python main.py "url:https://exemplo.com/artigo"
```

O Claude identifica o tipo de conteúdo (notícia, produto, humor, etc.) e adapta o tom. Não requer configuração prévia.

### Replay de episódio já gerado

Reproduz um episódio do dia no horário atual, sem chamar a API nem gerar novo áudio.
O argumento é um prefixo parcial do nome da pasta — quanto mais específico, mais preciso o match.

```bash
python main.py replay:12-15              # tudo gerado às 12:15
python main.py replay:12-15_not         # 12:15 cujo nome começa com "not" (ex: noticias)
python main.py replay:12-15_youtube     # apenas o episódio de youtube das 12:15
python main.py replay:noticias          # qualquer episódio de noticias do dia (sem filtro de hora)
python main.py replay:12-15 replay:14-30_filmes   # múltiplos replays de uma vez
```

Se nenhuma pasta bater com o prefixo, o comando exibe a lista de episódios disponíveis no dia.

> O replay não copia o arquivo MP3 — cria apenas um `episode.json` apontando para o original. O player detecta e reproduz normalmente.

### Parâmetros numéricos

```bash
python main.py musica:5       # bloco musical com 5 faixas
python main.py horoscopo:0    # Áries e Touro
python main.py horoscopo:3    # Libra e Escorpião
```

### Download de músicas (Jamendo)

```bash
python main.py download-musica
```

Baixa faixas do Jamendo para o cache local (`music/cache/jamendo/`) sem gerar episódio. Útil para popular o fallback antes de receber o primeiro episódio ou para ampliar a variedade musical.

O `serve.py` também faz esse download automaticamente na primeira inicialização, se o cache estiver vazio e o Jamendo estiver configurado.

O número de faixas baixadas por execução é controlado pelo parâmetro `cache_size` (padrão: 50):

```yaml
- id: musica
  type: music
  settings:
    source: jamendo
    cache_size: 100   # máximo de faixas a baixar por execução (padrão: 50)
    jamendo:
      api_key_env: JAMENDO_CLIENT_ID
      tags: lounge
```

### Player web

```bash
python serve.py
```

Abre automaticamente em `http://localhost:5000`. O player:
- Lista episódios organizados por dia
- Reproduz automaticamente na ordem de geração
- Retoma de onde parou após reload (posição salva no `localStorage`)
- Detecta novos episódios a cada 60 segundos (toast de notificação)
- Anuncia a hora no topo de cada hora e entre episódios (Web Speech API, cooldown de 20 min)
- Exibe o próximo item da grade ao final da playlist do dia atual
- Entra em modo musical (músicas da pasta `music/`) quando não há episódios novos, com aviso de voz
- No modo musical, intercala avisos de voz com os próximos itens da grade entre as músicas
- Mantém a tela ativa enquanto o áudio toca (Wake Lock API — Chrome Android e Safari iOS 16.4+)
- **Responsivo para mobile**: navegação por abas (Dias / Playlist / Fontes) na parte inferior

### Avisos de grade (breaks musicais)

Durante o modo musical, a cada `ANNOUNCEMENT_EVERY` faixas (padrão: 3) o player intercala um aviso de voz com a hora atual e os próximos itens agendados:

> *"São nove horas e quinze minutos. Você está na RadioIA. Em breve: Notícias do Dia às 9h30, Quiz do Dia às 10h e Horóscopo às 10h30."*

O áudio é gerado com a voz configurada em `vinheta.voice` e cacheado até o próximo item da grade passar — a regeneração acontece em background, sem interromper a reprodução.

Para desativar:

```yaml
announcements:
  enabled: false
```

### Clips de hora (speaking clock)

Os avisos de hora usam clips de áudio pré-gravados para evitar latência. O sistema mantém **83 clips atômicos** (24 horas + 59 minutos) e os combina em tempo de execução para cada HH:MM — o resultado é salvo em `output/_time_clips/` e reutilizado sem novo TTS.

Os clips são gerados automaticamente em background quando o `serve.py` inicia. Para gerá-los manualmente com antecedência:

```bash
python main.py --gen-time-clips           # gera os que faltam (~1 min)
python main.py --gen-time-clips --force   # regenera todos (ex: mudou a voz)
```

Se os clips ainda não existirem, o aviso é servido sem a hora — sem erro nem interrupção.

Para acessar pelo celular na mesma rede Wi-Fi:
```bash
ipconfig    # Windows — anote o "Endereço IPv4"
# Acesse http://<IP>:5000 no browser do celular
```

---

## Demonstração

### Interface web

| Desktop | Mobile |
|---------|--------|
| ![Interface desktop](docs/ui-desktop.png) | ![Interface mobile](docs/ui-mobile.png) |

### Scheduler no terminal

![Scheduler](docs/scheduler.png)

### Exemplo de episódio

[▶ Ouvir exemplo (MP3)](docs/episode.mp3)

---

## Programação automática (Scheduler)

### Configurar a grade

No `config.yaml`, adicione a seção `schedule`:

```yaml
schedule:
  # Diário — roda todo dia no horário indicado
  - time: "07:00"
    label: "Manhã"
    sources: [utilidades, noticias-locais]

  - time: "09:00"
    label: "Notícias"
    sources: [noticias, tecnologia]

  # Pontual — roda uma única vez na data indicada
  - time: "11:00"
    date: "2026-06-11"
    label: "Abertura da Copa"
    sources: [copa]
```

### Filtro por dia da semana (`days`)

Por padrão, todas as entradas rodam todos os dias. O campo `days` limita a execução a dias específicos, permitindo grades diferentes para semana e fim de semana.

```yaml
schedule:
  # Roda apenas nos dias úteis
  - time: "09:00"
    label: "Notícias da Semana"
    sources: [noticias, tecnologia]
    days: [mon, tue, wed, thu, fri]

  # Mesmo horário, conteúdo diferente no fim de semana
  - time: "09:00"
    label: "Fim de Semana"
    sources: [musica, receitas]
    days: [sat, sun]

  # Sem 'days' = todos os dias (padrão)
  - time: "07:00"
    label: "Manhã"
    sources: [utilidades, noticias-locais]
```

**Abreviações disponíveis:** `mon` `tue` `wed` `thu` `fri` `sat` `sun`

Na listagem do scheduler, entradas com filtro exibem os dias entre colchetes:
```
  09:00  diario  noticias tecnologia [mon,tue,wed,thu,fri] — Notícias da Semana
  09:00  diario  musica receitas [sat,sun] — Fim de Semana
```

---

### Replay de episódios (`slot_id` / `replay_of`)

Permite reaproveitar um episódio já gerado em outro horário da grade, sem nova chamada à API. Útil para conteúdos que não mudam ao longo do dia (filmes, horóscopo, etc.).

> **Replay ad-hoc pela linha de comando:** para repetir um episódio agora, fora da grade, use `python main.py replay:12-15_noticias` — veja a seção [Replay de episódio já gerado](#replay-de-episódio-já-gerado).

**Como funciona:**
1. Marque o slot gerador com `slot_id: <número>`
2. Nos slots de replay, use `replay_of: <número>` no lugar de `sources`
3. O scheduler cria uma pasta de replay na hora marcada, apontando para o áudio original — sem duplicar o arquivo MP3
4. O player detecta o episódio apenas na hora agendada

```yaml
schedule:
  # Gera o episódio e registra com id 10
  - time: "08:00"
    slot_id: 10
    label: "Cine Indica Manhã"
    sources: [filmes]

  # Gera outro episódio e registra com id 15
  - time: "10:00"
    slot_id: 15
    label: "Cine Indica"
    sources: [filmes]

  # Replay do slot 10 (episódio das 08:00) — sem nova geração
  - time: "14:00"
    replay_of: 10
    label: "Cine Indica (tarde)"

  # Replay do slot 15 (episódio das 10:00)
  - time: "16:00"
    replay_of: 15
    label: "Cine Indica (noite)"
```

> Se `replay_of` chegar antes do episódio original ser gerado, o scheduler avisa e pula — sem travar nem gerar duplicata.

A grade exibe `[slot:10]` nos entradas geradoras e `replay:10` nas de replay.

### Comandos do scheduler

```bash
python scheduler.py           # inicia o agendador
python scheduler.py --list    # exibe a grade sem rodar
pythonw scheduler.py          # inicia sem janela de terminal (Windows)
```

O scheduler recarrega o `config.yaml` a cada verificação — editar a grade não exige reiniciar.

O estado das execuções é salvo em `scheduler_state.json`:
- Entradas **diárias** são marcadas como executadas no dia e resetam à meia-noite
- Entradas **pontuais** são marcadas como concluídas permanentemente após rodar
- **`programacao_map`** registra o mapeamento `slot_id → episódio` do dia corrente

---

## Servidor MCP

O `mcp_server.py` expõe a RadioIA como um servidor [MCP (Model Context Protocol)](https://modelcontextprotocol.io), permitindo que agentes de IA (como o Claude no Claude Code) gerem episódios diretamente por conversa.

### Iniciar o servidor

```bash
python mcp_server.py
```

### Ferramentas disponíveis

| Ferramenta | Descrição |
|-----------|-----------|
| `listar_fontes()` | Lista todas as fontes configuradas e o estado do histórico |
| `gerar_episodios(["noticias", "copa"])` | Gera episódios para as fontes especificadas |
| `gerar_episodios(["filmes"])` | Gera quadro de indicações de filmes (TMDB trending) |
| `gerar_episodios(["filmes-cartaz"])` | Gera quadro de filmes em cartaz no Brasil |
| `gerar_episodios(["url:https://..."])` | Gera episódio a partir de uma URL avulsa |
| `listar_episodios("2026-06-11")` | Lista episódios gerados em uma data (padrão: hoje) |
| `replay_episodio("12-15_not")` | Replay de episódio por prefixo parcial da pasta (hoje) |
| `replay_episodio("12-15", "2026-06-03")` | Replay de episódio de uma data específica |
| `status_historico()` | Mostra quantos itens já foram veiculados |
| `limpar_historico()` | Reseta o histórico — todos os conteúdos ficam elegíveis novamente |

**Fontes disponíveis em `gerar_episodios`:**
`youtube` · `noticias` · `noticias-locais` · `tecnologia` · `horoscopo` · `utilidades` · `loteria` · `copa` · `brasileirao` · `champions` · `efemerides` · `quiz` · `reddit` · `receitas` · `filmes` · `filmes-cartaz` · `musica` · `musica-local`

### Configurar no Claude Code (`~/.claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "radioIA": {
      "command": "python",
      "args": ["C:/caminho/para/radioIA/mcp_server.py"]
    }
  }
}
```

Após configurar, você pode pedir ao Claude: *"Gera um episódio de notícias e copa do mundo"* e ele executa diretamente.

---

## Estrutura de saída

Os episódios são salvos em:

```
output/
  2026-06-11/
    09-00_noticias/
      episode.mp3       ← áudio do episódio
      episode.json      ← metadados (fontes, links, duração)
    12-00_copa/
      episode.mp3
      episode.json
```

---

## Estrutura do projeto

```
radioIA/
├── main.py                      # ponto de entrada principal
├── serve.py                     # player web (Flask)
├── scheduler.py                 # agendador de episódios
├── mcp_server.py                # servidor MCP para agentes de IA
├── config.yaml                  # configuração completa
├── .env                         # chaves de API (não versionar)
├── src/
│   ├── script_generator.py      # geração de roteiros (LiteLLM — multi-provedor)
│   ├── tts_generator.py         # síntese de voz (multi-provedor)
│   ├── audio_mixer.py           # mixagem e exportação do episódio
│   ├── vinheta.py               # geração das vinhetas
│   ├── time_clips.py            # clips de hora/minuto para avisos de grade
│   ├── history.py               # controle de itens já veiculados
│   ├── spots.py                 # sistema de spots (propagandas/comunicados)
│   ├── auth.py                  # autenticação OAuth YouTube
│   ├── text_utils.py            # normalização de texto para TTS
│   ├── sources/                 # fontes de infraestrutura (core)
│   │   ├── youtube.py           # fonte YouTube (requer OAuth)
│   │   ├── rss.py               # fonte RSS genérica
│   │   ├── music.py             # blocos musicais (Jamendo + local)
│   │   └── utility.py           # clima, finanças, loteria, futebol
│   └── tts_providers/           # providers de síntese de voz
│       ├── edge_tts_provider.py # Edge TTS — padrão, gratuito
│       ├── openai_provider.py   # OpenAI TTS (tts-1 / tts-1-hd)
│       ├── elevenlabs_provider.py # ElevenLabs
│       └── google_provider.py   # Google Cloud TTS
├── plugins/                     # fontes de conteúdo (carregadas automaticamente)
│   ├── efemerides.py            # hoje na história (Wikipedia)
│   ├── trivia.py                # quiz (Open Trivia DB)
│   ├── reddit.py                # Reddit (top posts via RSS)
│   ├── horoscopo.py             # horóscopo por signo (Personare)
│   ├── receitas.py              # receitas culinárias (RSS + TheMealDB)
│   ├── filmes.py                # indicações de filmes (TMDB)
│   ├── url.py                   # episódio a partir de URL avulsa
│   ├── biblia.py                # passagens bíblicas (ABíbliaDigital)
│   ├── concursos_pci.py         # concursos públicos (PCI Concursos)
│   ├── clipping.py              # panorama de cobertura midiática sobre um tema
│   ├── whatsapp.py              # resumo de grupo WhatsApp (exportação manual)
│   └── exemplo_plugin.py        # template para novos plugins
├── music/                       # músicas locais para o fallback do player
└── output/                      # episódios gerados (não versionar)
```

---

## Adicionando novos feeds RSS

Basta adicionar uma entrada em qualquer fonte `type: rss` no `config.yaml`:

```yaml
feeds:
  - url: "https://exemplo.com.br/feed"
    name: "Nome do Veículo"
```

---

## Spots (propagandas e comunicados)

Spots são clipes de áudio curtos injetados automaticamente durante a programação. Suportam três origens e rotação configurável.

### Origens

| Tipo | Descrição | Quando usar |
|------|-----------|-------------|
| `file` | MP3 pré-gravado fornecido pelo usuário | Áudio produzido externamente com qualidade profissional |
| `tts` | Texto convertido em voz (edge-tts) | Comunicados rápidos com a mesma voz da rádio |
| `llm` | Tema → LLM → voz (script gerado diariamente) | Conteúdo variado e dinâmico sem esforço de produção |

### Configuração

```yaml
spots:
  - id: promo-evento
    type: file
    path: "spots/evento.mp3"
    weight: 2          # toca 2× mais que os outros (padrão: 1)
    max_per_day: 5     # limite por ouvinte por dia

  - id: aviso-reuniao
    type: tts
    text: "Atenção colaboradores: reunião geral às 15h na sala principal."
    # voice: "pt-BR-AntonioNeural"   # opcional — usa vinheta.voice se omitido

  - id: chamada-produto
    type: llm
    topic: "Promova o produto XYZ de forma descontraída em 20 segundos"
    duration_seconds: 20
    max_per_day: 3
    # model: "claude-haiku-4-5-20251001"   # opcional — usa llm.model se omitido
```

### Pontos de injeção

```yaml
spots_config:
  fallback_every: 5            # a cada N músicas no modo fallback (0 = desativado)
  between_episodes_every: 3   # a cada N transições entre episódios (0 = desativado)
```

Com `between_episodes_every: 3`: episódio 1 → 2 → 3 → **break** → 4 → 5 → 6 → **break** → ...

Quando ambos spot e anúncio de grade disparam no mesmo break, a ordem é: **spot → anúncio → próximo episódio/música**.

### Rotação e limites

- **`weight`** — frequência relativa entre spots (servidor)
- **`max_per_day`** — limite de reproduções por ouvinte por dia (cliente, via `localStorage`)
- Nunca repete o mesmo spot duas vezes consecutivas

### Spot como fonte agendável

Para inserir um spot em horário fixo na grade (aparece na playlist):

```yaml
sources:
  - id: comunicado
    type: spot
    name: "Comunicado"
    enabled: true

schedule:
  - time: "10:00"
    sources: [comunicado]
```

### Cache de áudio

- `type: file` — lido do disco a cada uso
- `type: tts` — gerado uma vez e salvo em `output/_spots/{id}.mp3`
- `type: llm` — gerado uma vez por dia e salvo em `output/_spots/{id}-{data}.mp3`; o script gerado fica em `.txt` no mesmo diretório para inspeção

---

## Rádio Corporativa

O RadioIA pode ser adaptado para uso como **rádio interna de empresa** — veiculando comunicados, resultados, agenda e cultura organizacional de forma automática, sem equipe de rádio dedicada.

Para dar a identidade da empresa à rádio, basta editar `radio.name` no `config.yaml` (veja a seção [Nome da rádio](#nome-da-rádio)). O nome aparece nos roteiros narrados, nas vinhetas de entrada e encerramento, nas tags MP3 e na interface web — sem nenhuma outra alteração.

### Conteúdos e como implementar

| Conteúdo | Como implementar |
|----------|-----------------|
| Notícias do setor da empresa | `type: rss` apontando para feeds do segmento (ex: agro, varejo, saúde) |
| Cotações relevantes ao negócio | `type: utility` — adicionar pares de câmbio ou tickers da empresa em `finance.pairs` |
| Resultados de competições esportivas | `type: utility` com `football` ou estender para outros esportes |
| Quiz de capacitação / compliance | `type: trivia` com banco de perguntas próprio (requer integração com Open Trivia DB ou API interna) |
| Curiosidades históricas da empresa | `type: efemerides` adaptado para uma base de dados interna (ex: "hoje faz X anos que fundamos a empresa") |
| Música ambiente | `type: music` com `source: local` apontando para pasta com músicas licenciadas da empresa |
| Comunicados internos | Novo módulo `type: comunicados` lendo de SharePoint, intranet ou e-mail corporativo via API |
| KPIs e metas do período | Novo módulo `type: kpis` integrando com BI (Power BI, Metabase) ou ERP via API REST |
| Cardápio do refeitório | Novo módulo `type: cardapio` lendo de planilha, sistema próprio ou e-mail diário |
| Aniversários e boas-vindas | Novo módulo `type: pessoas` integrando com Active Directory, TOTVS ou qualquer HR system |
| Vagas internas | Novo módulo `type: vagas` lendo de ATS interno (Gupy, Workday, etc.) |
| Reconhecimentos de equipe | Novo módulo alimentado manualmente ou via formulário (Google Forms → Sheets → RSS) |

### Arquitetura para o contexto corporativo

O sistema já é modular por design: cada fonte de conteúdo é um arquivo Python independente em `src/sources/`. Para criar um novo módulo basta implementar a função `fetch(source_config, credentials) -> list[dict]` retornando itens no formato padrão — o roteador em `main.py` e o gerador de roteiros em `script_generator.py` cuidam do resto.

Os itens devem seguir este formato:

```python
{
    'id':           'identificador-unico',   # usado para evitar repetição
    'title':        'Título do conteúdo',
    'url':          'https://...',           # link de referência (pode ser vazio)
    'text':         'Texto completo...',     # conteúdo que o Claude vai narrar
    'source_name':  'Nome da Fonte',
    'source_type':  'tipo_do_modulo',
    'published_at': '2026-06-02',
    'views':        0,
    'comments':     [],
    'channel':      'Setor ou Categoria',
}
```

### Considerações para implantação

- **Privacidade:** conteúdos internos não devem passar pela API da Anthropic sem avaliação jurídica. Considere usar modelos locais (Ollama + LLaMA) no lugar do Claude para dados sensíveis.
- **Infraestrutura:** o sistema roda em qualquer máquina Windows/Linux/macOS com Python. Para uso contínuo, recomenda-se rodar o `scheduler.py` como serviço (systemd no Linux, Task Scheduler no Windows).
- **Player:** o `serve.py` é um servidor web simples acessível por qualquer dispositivo na rede local — basta abrir `http://<IP-do-servidor>:5000` no browser, sem instalação nos clientes.
- **Vozes:** o Edge TTS usa as vozes da Microsoft, que requerem conexão com a internet. Para ambientes offline, substituir por um motor TTS local (ex: Coqui TTS).

---

## Geradores personalizados (plugins)

Coloque arquivos `.py` na pasta `plugins/` para adicionar novos tipos de conteúdo sem modificar o projeto. O RadioIA os carrega automaticamente ao iniciar.

```
plugins/
  meu_gerador.py    ← carregado e disponível como type: meu_gerador
```

### Plugins incluídos

| Plugin | `type` | Descrição | Requisitos |
|--------|--------|-----------|------------|
| `concursos_pci.py` | `concursos_pci` | Notícias de concursos públicos (PCI Concursos) | `beautifulsoup4`, `trafilatura` |
| `biblia.py` | `biblia` | Passagens bíblicas com reflexão (ABíbliaDigital) | `requests`, token em `ABIBLIADIGITAL_TOKEN` |
| `clipping.py` | `clipping` | Panorama de como a mídia cobre um tema — gerado via CLI | — |
| `whatsapp.py` | `whatsapp` | Resumo de grupo do WhatsApp a partir de exportação manual | — |

**Configuração do plugin Bíblia** (`config.yaml`):

```yaml
- id: biblia
  type: biblia
  name: "Palavra do Dia"
  enabled: true
  settings:
    token_env: ABIBLIADIGITAL_TOKEN   # token gratuito em abibliadigital.com.br
    version: nvi                      # nvi | acf | ra | kjv
    mode: random                      # random | book | passage
    # book: sl                        # livro específico (mode: book)
    # passage: jo:3:16                # referência exata (mode: passage)
    max_items: 1
```

**Configuração do plugin WhatsApp** (`config.yaml`):

Exporte a conversa pelo WhatsApp: **Grupo → ⋮ → Mais → Exportar conversa → Sem mídia**. Configure um `id` diferente para cada grupo.

```yaml
- id: grupo-trabalho
  type: whatsapp
  name: "Grupo do Trabalho"
  enabled: true
  settings:
    path: "/caminho/para/exportacao.zip"   # arquivo .zip ou pasta com vários .zips
    days_lookback: 1                        # quantos dias incluir no episódio
    max_messages: 150                       # limite de mensagens enviadas ao LLM
    ignore_media: true                      # ignora linhas de mídia (foto, vídeo, áudio)
```

Suporta os formatos de exportação Android e iOS. Se `path` for uma pasta, usa o `.zip` modificado mais recentemente. Múltiplos grupos podem ser configurados com ids distintos e o mesmo `type: whatsapp`.

**Plugin Clipping** — panorama de cobertura midiática:

Busca no Google News como diferentes veículos estão abordando um tema e gera um episódio no estilo "o que a imprensa está dizendo sobre X". Não requer entrada no `config.yaml` — o tópico é sempre passado via CLI:

```bash
python main.py "clipping:queda de avião da empresa xyz"
python main.py "clipping:eleições municipais 2026"
python main.py "clipping:nova atualização do iPhone"
```

O episódio compara os ângulos de cada veículo ("O G1 destaca...", "Segundo a CNN Brasil..."), aponta convergências e divergências, e exibe todos os links nas notas do player. Para personalizar os defaults, adicione ao `config.yaml`:

```yaml
- id: clipping
  type: clipping
  name: "Clipping"
  enabled: true
  settings:
    max_sources: 5          # máximo de veículos a incluir (padrão: 5)
    days_lookback: 1        # só artigos dos últimos N dias (padrão: 1)
    fetch_content: true     # extrai texto completo via trafilatura (padrão: true)
    max_content_chars: 2000 # limite de caracteres por artigo (padrão: 2000)
```

Consulte o guia completo com contrato, exemplos e boas práticas:

🔌 **[docs/criando-geradores.md](docs/criando-geradores.md)**

---

## Modo Streamer (opcional)

Para transmitir o RadioIA como uma rádio ao vivo usando Icecast2 + Liquidsoap, consulte o guia:

📡 **[docs/streaming.md](docs/streaming.md)**

O pipeline de geração (scheduler, episódios, músicas) não muda — apenas a camada de entrega é substituída.

---

## Observações

- O histórico de itens já veiculados é salvo em `history.json`. Isso evita repetição de conteúdo entre execuções.
- A pasta `music/` aceita arquivos `.mp3`, `.m4a`, `.ogg`, `.wav` e `.flac` para o modo fallback do player.
- A ordem dos feeds RSS é embaralhada a cada execução para garantir diversidade entre as fontes.
- O ffmpeg é necessário para a mixagem de áudio. Certifique-se de que está no PATH do sistema.
