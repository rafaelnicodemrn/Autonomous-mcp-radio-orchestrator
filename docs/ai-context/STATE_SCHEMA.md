# Schemas de Estado — RadioIA

Os dois arquivos de estado runtime na raiz do projeto. **Não commitar**
(contêm dados pessoais de uso — ver [CLAUDE.md](../../CLAUDE.md)).

## `telegram_state.json`

Gerenciado por `load_state()`/`save_state()` em `telegram_bot.py`.

```json
{
  "chat_id": 7828252657,
  "last_briefing": "2026-06-11T04:10:30.370000",
  "sent_item_ids": ["c8627e46c100", "86f5797be19a", "..."],
  "config": {
    "briefing_time": "07:00",
    "include_audio": true,
    "max_items_per_category": 3
  }
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `chat_id` | `int \| null` | ID do chat Telegram do Rafael; preenchido por `/start` (e mantido em sincronia com `TELEGRAM_CHAT_ID` no `.env`). `null`/ausente → briefing matinal aborta (ver [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)). |
| `last_briefing` | `string (ISO datetime) \| null` | Timestamp do último briefing matinal enviado com sucesso. Atualizado ao final de `send_morning_briefing`. |
| `sent_item_ids` | `string[]` | Lista FIFO (máx. `MAX_SENT_IDS=500`) de `item_hash(item)` (`md5(f"{source_id}/{id ou title}")[:12]`) já enviados — evita duplicar conteúdo entre execuções. |
| `config.briefing_time` | `string "HH:MM"` | Horário nominal do briefing (referência; o agendamento real usa `BRIEFING_HOUR`/`BRIEFING_MINUTE` em `telegram_bot.py`). |
| `config.include_audio` | `bool` | Flag de referência para envio de áudio (uso informativo). |
| `config.max_items_per_category` | `int` | Quantos itens por seção/fonte são enviados no briefing matinal (default 3); também usado como base para `max_items_per_category * 3` nos comandos on-demand. |

## `adaptive_state.json`

Gerenciado por `load_adaptive_state()`/`save_adaptive_state()` em
`src/adaptive_engine.py`. `load_adaptive_state()` faz backfill de chaves
ausentes a partir de `DEFAULT_STATE` — arquivos antigos continuam
compatíveis. Ver [ADAPTIVE_SYSTEM.md](../ADAPTIVE_SYSTEM.md) para a lógica
completa.

```json
{
  "source_reputation": {},
  "feedback_history": [],
  "youtube_interest_vector": {},
  "command_usage": {},
  "signal_weights": {
    "llm": 0.7,
    "reputation": 0.0,
    "recency": 0.3,
    "feedback": 0.0,
    "youtube": 0.0
  },
  "last_youtube_sync": null,
  "last_auto_analysis": null,
  "total_items_processed": 0,
  "total_feedback_given": 0,
  "auto_adjustments_log": []
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `source_reputation` | `{ [source_name]: { avg: number, count: int } }` | Média móvel (`avg`, 0–10) e contagem de pontuações Gemini recebidas por fonte. Atualizado por `update_source_reputation` em `filter_and_score_items` (passo 4) e em `record_feedback`. `avg` inicial = 5.0. |
| `feedback_history` | `Array<FeedbackEntry>` | Histórico FIFO (máx. `MAX_FEEDBACK_HISTORY=500`) de feedbacks 👍/👎. Cada entrada: `{item_hash, source_name, source_id, gemini_score, feedback, timestamp}` — `feedback` é `"+1"` ou `"-1"`, `source_name`/`source_id` são as versões curtas (`src_short`/`sid_short`) usadas no `callback_data`. Consumido por `_calc_feedback_score` (janela `FEEDBACK_WINDOW_DAYS=30`). |
| `youtube_interest_vector` | `{ [interesse]: number (0.0–1.0) }` | Vetor de interesses inferido pelo Gemini a partir de vídeos curtidos/histórico (`sync_youtube_signals`). Vazio até a primeira sincronização (`/sincronia` ou briefing matinal). Ex.: `{"catolicismo": 0.85, "tecnologia": 0.72}`. |
| `command_usage` | `{ [cmd_key]: int }` | Contador de uso por comando (ex. `"/fe": 23`), incrementado por `record_command_usage` em `cmd_generate`. Usado no relatório de `run_weekly_analysis`. |
| `signal_weights` | `{ llm, reputation, recency, feedback, youtube: number }` | Pesos atuais (somam ~1.0) usados em `compute_adaptive_score`. Recalculado por `calculate_dynamic_weights` — ver tabela de 5 estágios em [ADAPTIVE_SYSTEM.md](../ADAPTIVE_SYSTEM.md#pesos-dinâmicos-calculate_dynamic_weights). Estado inicial: `{llm: 0.70, reputation: 0.0, recency: 0.30, feedback: 0.0, youtube: 0.0}`. |
| `last_youtube_sync` | `string (YYYY-MM-DD) \| null` | Data da última sincronização do YouTube; comparado com "hoje" no briefing matinal para decidir se sincroniza novamente. |
| `last_auto_analysis` | `string (ISO datetime) \| null` | Timestamp da última execução de `run_weekly_analysis` (manual via `/analise` ou agendada `weekly_analysis_job`). |
| `total_items_processed` | `int` | Contador acumulado de itens que passaram por `filter_and_score_items`. |
| `total_feedback_given` | `int` | Contador acumulado de feedbacks 👍/👎 recebidos (incrementado em `record_feedback`). |
| `auto_adjustments_log` | `Array<{date: string, report_preview: string}>` | Histórico FIFO (máx. `MAX_ADJUSTMENTS_LOG=20`) dos relatórios de `run_weekly_analysis` — `report_preview` é o relatório truncado em 100 caracteres. Puramente informativo; não há ajuste automático de pesos/perfil a partir daqui. |

### Exemplo após algum uso (ilustrativo)

```json
{
  "source_reputation": {
    "PadrePauloR": {"avg": 8.4, "count": 12},
    "G1": {"avg": 5.9, "count": 30}
  },
  "feedback_history": [
    {"item_hash": "a1b2c3d4", "source_name": "PadrePauloR", "source_id": "catolici", "gemini_score": 8, "feedback": "+1", "timestamp": "2026-06-10T08:15:00"}
  ],
  "youtube_interest_vector": {"catolicismo": 0.85, "tecnologia": 0.72, "futebol": 0.61},
  "command_usage": {"/fe": 23, "/tech": 14, "/briefing": 56},
  "signal_weights": {"llm": 0.35, "reputation": 0.20, "recency": 0.15, "feedback": 0.20, "youtube": 0.10},
  "last_youtube_sync": "2026-06-13",
  "last_auto_analysis": "2026-06-08T08:00:00",
  "total_items_processed": 412,
  "total_feedback_given": 23,
  "auto_adjustments_log": [
    {"date": "2026-06-08T08:00:00", "report_preview": "Você demonstra forte interesse em conteúdo católico e do Grêmio..."}
  ]
}
```
