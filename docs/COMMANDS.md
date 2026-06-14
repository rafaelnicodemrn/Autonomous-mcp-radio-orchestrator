# Comandos do Bot Telegram — RadioIA

Todos os comandos são registrados em `telegram_bot.py: main()`. Os comandos
de geração (segunda tabela) compartilham o handler genérico `cmd_generate`,
disparam `main.py` como subprocesso e passam pelo pipeline
`_send_items` (enriquecimento → dedup → filtragem por perfil → recálculo
adaptativo → quotas → diversidade → envio com botões de feedback).

## Comandos estáticos

### `/start`
Registra o `chat_id` atual em `telegram_state.json` e no `.env`
(`TELEGRAM_CHAT_ID`), e envia a lista completa de comandos disponíveis.

```
/start
```
> 📻 RadioIA Pessoal
> Seu briefing diário de notícias, fé e futebol.
> ━━━━━━━━━━━━━━━━━━━━
> 📋 Comandos disponíveis:
> /briefing — Briefing completo agora
> ... (lista completa)
> ⏰ Briefing automático às 07:00 todos os dias.

### `/ajuda`
Alias de `/start` (mesma saída).

### `/status`
Mostra o status operacional do bot.

```
/status
```
> 📊 Status do RadioIA Bot
> 💬 Chat ID: 7828252657
> 📅 Último briefing: 2026-06-13T07:00:12
> 📦 Itens no histórico: 187
> ⏰ Próximo briefing: 07:00

### `/historico`
Lista os episódios gerados hoje (`output/<YYYY-MM-DD>/`), com botão "🎵 play"
para os que têm `episode.mp3`.

```
/historico
```
> 📋 Episódios de hoje:
> 1. 07h00 — Fé e Reflexão · 3:42
> 2. 07h05 — Notícias do Dia · 5:10
>
> [🎵 Fé e Reflexão] [🎵 Notícias do Dia]

Tocar no botão envia o áudio do episódio (`callback_play`, padrão
`play:<folder>`).

### `/perfil [...]`
Ver e editar o perfil de interesses (`telegram.perfil` em `config.yaml`).

- `/perfil` — mostra o perfil atual (interesses, fontes VIP, lista de
  ignorados, score mínimo, máx. cards, idioma).
- `/perfil ajuda` — mostra a sintaxe de edição.
- `/perfil add interesse <texto>` — adiciona a `interesses_primarios`.
- `/perfil rem interesse <texto>` — remove (busca por substring,
  case-insensitive).
- `/perfil add ignorar <texto>` / `/perfil rem ignorar <texto>` — gerencia
  `ignorar_sempre`.
- `/perfil add vip <nome da fonte>` / `/perfil rem vip <nome da fonte>` —
  gerencia `fontes_vip`.
- `/perfil set score <0-10>` — define `score_minimo_enviar`.
- `/perfil set cards <1-20>` — define `max_cards_por_comando`.

```
/perfil add interesse economia austríaca
```
> ✅ Adicionado aos seus interesses: **economia austríaca**

```
/perfil set score 6
```
> ✅ Score mínimo alterado para **6/10**
> _Notícias com score abaixo de 6 não serão enviadas._

### `/url <link>`
Gera um episódio a partir de uma URL avulsa (`plugins/url.py`, suporta
artigos via `trafilatura` e vídeos do YouTube via transcrição). Envia até 3
itens resultantes.

```
/url https://www.brasilparalelo.com.br/artigos/exemplo
```
> ⏳ Gerando episódio a partir de:
> https://www.brasilparalelo.com.br/artigos/exemplo
>
> Aguarde alguns minutos...
>
> (cards do conteúdo extraído, com botões 👍/👎)

### `/aprendizado`
Mostra o status do motor de aprendizado adaptativo
(`format_learning_status`). Ver [ADAPTIVE_SYSTEM.md](ADAPTIVE_SYSTEM.md).

```
/aprendizado
```
> 🧠 Status de Aprendizado — RadioIA
>
> 📊 Dados acumulados:
> • Feedbacks dados: 23 (18 👍 / 5 👎)
> • Fontes avaliadas: 12
> • Interesses mapeados (YouTube): 4
> • Comandos usados: 56
>
> ⭐ Melhores fontes (por você):
> • Padre Paulo Ricardo — 9.1/10
> • Vatican News PT — 8.7/10
> • Grêmio Oficial — 8.2/10
>
> ⚙️ Pesos ativos:
> • LLM: 40% | Reputação: 25% | Recência: 20%
> • Feedback: 15% | YouTube: 0%
>
> 📅 Última análise automática: 08 jun 2026

### `/analise`
Roda a análise semanal sob demanda (`run_weekly_analysis`), gerando um
relatório via Gemini com base nos dados acumulados.

```
/analise
```
> 🧠 Analisando seus dados de uso...
>
> (relatório gerado pelo Gemini — máx. 10 linhas, com insights e sugestão de
> ajuste)

Se houver menos de 3 feedbacks e nenhuma fonte avaliada:
> Ainda sem dados suficientes para análise. Continue usando o bot!

### `/sincronia`
Força a sincronização do `youtube_interest_vector` a partir dos vídeos
curtidos/histórico do YouTube (requer `credentials.json`/`token.json`
válidos via `src/auth.py`).

```
/sincronia
```
> ▶️ Sincronizando preferências do YouTube...
>
> ✅ Interesses identificados: catolicismo (0.85), tecnologia (0.72), futebol (0.61)

Se não houver credenciais configuradas:
> ⚠️ Credenciais do YouTube não configuradas.

### `/config`
Mostra as quotas configuradas por comando (`telegram.quotas`) e os pesos
atuais do motor adaptativo (`signal_weights`).

```
/config
```
> ⚙️ Configurações — RadioIA
>
> 📦 Quotas por comando:
> • /briefing: até 3/fonte, máx 15 total
> • /tech: até 3/fonte, máx 8 total
> • /fe: até 3/fonte, máx 8 total
> • /gremio: até 3/fonte, máx 8 total
> • /noticias: até 3/fonte, máx 8 total
> • /filmes: até 3/fonte, máx 8 total
> • /local: até 3/fonte, máx 8 total
>
> 🧠 Pesos do motor adaptativo:
> • llm: 40%
> • reputation: 25%
> • recency: 20%
> • feedback: 15%
> • youtube: 0%

## Comandos de geração (on-demand)

Todos seguem o padrão: avisam que estão gerando, executam `main.py` com as
fontes correspondentes (timeout 360s), buscam vídeos extras do YouTube por
keyword (`YOUTUBE_KEYWORDS`), e enviam os itens via `_send_items`.

### `/briefing`
Fontes: `biblia, utilidades, catolicismo, noticias, tecnologia, politica,
conservadorismo, gdelt`. Keywords YouTube: "notícias Brasil hoje",
"principais acontecimentos".

```
/briefing
```
> ⏳ Gerando **Briefing**...
> Aguarde alguns minutos.
>
> ✅ **Briefing** — 14 item(s) encontrado(s)
> (cards de cada fonte, respeitando quota `briefing` — máx 3/fonte, 15 total)

### `/noticias`
Fontes: `noticias, politica, noticias-internacionais, gdelt`. Keywords:
"notícias Brasil política hoje", "Brasil governo semana". Quota: máx
3/fonte, 8 total.

### `/tech`
Fontes: `tecnologia, inteligencia-artificial, tecnologia-internacional`.
Keywords: "inteligência artificial novidades", "tecnologia lançamento".
Quota: máx 3/fonte, 8 total.

### `/fe`
Fontes: `biblia, catolicismo, conservadorismo`. Keywords: "catolicismo
reflexão", "Padre Paulo Ricardo". Quota: máx 3/fonte, 8 total.

```
/fe
```
> ⏳ Gerando **Fe**...
> Aguarde alguns minutos.
>
> ✅ **Fe** — 6 item(s) encontrado(s)
>
> ✝️ **Padre Paulo Ricardo**  ⭐⭐
> 📌 **[A virtude da paciência segundo Santo Tomás]**(...)
> • ...
> 🔗 Ler artigo completo
> #catolicismo
> [👍 Relevante] [👎 Não curto]

### `/gremio`
Fontes: `gremio, copa, brasileirao, libertadores`. Keywords: "Grêmio
futebol", "Brasileirão rodada resultado". Quota: máx 3/fonte, 8 total.

### `/filmes`
Fontes: `filmes, filmes-cartaz`. Keywords: "filmes lançamento 2026", "cinema
estreia". Quota: máx 3/fonte, 8 total.

### `/local`
Fontes: `noticias-locais, agronegocio`. Keywords: "agronegócio Brasil", "soja
milho mercado". Quota: máx 3/fonte, 8 total.

### `/youtube`
Fontes: `youtube` (canais configurados em `config.yaml: sources: - id:
youtube`). Não está em `YOUTUBE_KEYWORDS`, então não busca vídeos extras por
keyword — usa apenas o resultado de `main.py` para a fonte `youtube`. Sem
quota dedicada em `telegram.quotas`.

## Comandos removidos

`/reddit` e `/cultura` foram removidos do bot (Tarefa 1). A fonte `reddit`
(plugin `reddit.py`) continua presente em `config.yaml: sources:`, mas sem
comando dedicado — pode ser usada via `python main.py reddit` no terminal ou
reincluída em algum comando se desejado.

## Botões inline (callbacks)

| Pattern | Handler | Descrição |
|---|---|---|
| `^play:` | `callback_play` | Envia o `episode.mp3` da pasta indicada (`play:<folder>`) |
| `^fb:` | `callback_feedback` | Registra feedback 👍 (`+1`) / 👎 (`-1`) via `record_feedback`, remove o teclado da mensagem e agradece |

## Jobs agendados (`JobQueue`)

| Job | Frequência | Função |
|---|---|---|
| `briefing_matinal` | Diário, 07:00 (horário local) | `send_morning_briefing` |
| `analise_semanal` | Domingo, 08:00 | `weekly_analysis_job` (envia relatório de `run_weekly_analysis` via `/analise` automático) |
