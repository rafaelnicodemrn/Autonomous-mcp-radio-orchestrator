# Sistema Adaptativo de Aprendizado — RadioIA

Implementado em `src/adaptive_engine.py`, integrado em
`src/profile_filter.py` (recálculo de score) e `telegram_bot.py` (comandos
`/aprendizado`, `/analise`, `/sincronia`, `/config`, botões de feedback
👍/👎, sincronização automática no briefing matinal, análise semanal
agendada). Estado persistido em `adaptive_state.json` (raiz do projeto).

## Por que existe

O score que o Gemini atribui a um item (`score_batch_with_gemini`) reflete
apenas o "perfil declarado" (`interesses_primarios`, `fontes_vip`,
`ignorar_sempre`). O motor adaptativo complementa esse score com sinais
**observados** ao longo do tempo, para que o sistema aprenda na prática o
que o Rafael realmente lê/curte, sem precisar editar o perfil manualmente.

## Os 5 sinais

Cada item recebe um score final de 0 a 10
(`compute_adaptive_score`), calculado como soma ponderada de:

| Sinal | Função | Faixa | O que mede |
|---|---|---|---|
| **LLM** | (score do Gemini, `score_batch_with_gemini`) | 0–10 | Relevância segundo o perfil declarado |
| **Reputação** | `_calc_*` via `state['source_reputation'][source_name]['avg']` | 0–10 (default 5.0) | Média histórica dos scores do Gemini para aquela fonte |
| **Recência** | `_calc_recency(published_at)` | 2 / 5 / 7 / 10 | Quão recente é o item |
| **Feedback** | `_calc_feedback_score(source_name, state)` | 0–10 (default 5.0) | Reação 👍/👎 do usuário a itens daquela fonte (últimos 30 dias) |
| **YouTube** | `_calc_youtube_alignment(item, state)` | 0–10 (0 ou 5 se sem match) | Alinhamento do título/fonte com `youtube_interest_vector` |

### Fórmula final

```python
final = (
    weights['llm']        * gemini_score
    + weights['reputation'] * source_avg
    + weights['recency']    * recency_score
    + weights['feedback']   * feedback_score
    + weights['youtube']    * youtube_score
)
final = round(min(max(final, 0.0), 10.0), 1)
```

### Detalhe de cada sinal

- **Recência** (`_calc_recency`): hoje → 10, ontem → 7, 2 dias → 5, 3+ dias →
  2; sem `published_at` válido → 5.
- **Reputação** (`update_source_reputation`): média móvel —
  `new_avg = (old_avg * count + score) / (count + 1)`, começando de `avg=5.0`.
  Atualizada a cada item pontuado pelo Gemini (em
  `filter_and_score_items`, passo 4) **e** a cada feedback do Telegram
  (`record_feedback`).
- **Feedback** (`_calc_feedback_score`): considera feedbacks dos últimos 30
  dias (`FEEDBACK_WINDOW_DAYS`) para a mesma `source_name`.
  `ratio = soma(+1/-1) / total`; `score = 5 + ratio*5`, clamped 0–10. Sem
  histórico para a fonte → 5.0 (neutro).
- **YouTube** (`_calc_youtube_alignment`): se `youtube_interest_vector` está
  vazio → 5.0 (neutro). Caso contrário, verifica se alguma chave do vetor
  (interesse, lowercase) aparece em `title`+`source_name`; se houver matches,
  `score = média(pesos casados) * 10` (clamped 0–10); se não houver matches
  e o vetor não está vazio → 0.0 (penaliza itens fora dos interesses
  mapeados).

## Pesos dinâmicos (`calculate_dynamic_weights`)

Os pesos começam concentrados em LLM+Recência e vão se redistribuindo
conforme dados se acumulam. Critérios:

- `tem_feedback` = `len(feedback_history) >= 5`
- `tem_reputacao` = `len(source_reputation) >= 3`
- `tem_youtube` = `len(youtube_interest_vector) >= 3`

| Estágio | Condição | llm | reputation | recency | feedback | youtube |
|---|---|---|---|---|---|---|
| Inicial | nenhum sinal extra | 0.70 | 0.00 | 0.30 | 0.00 | 0.00 |
| Só reputação | `tem_reputacao` | 0.55 | 0.25 | 0.20 | 0.00 | 0.00 |
| Reputação + YouTube | `tem_reputacao and tem_youtube` | 0.45 | 0.25 | 0.20 | 0.00 | 0.10 |
| Feedback + Reputação | `tem_feedback and tem_reputacao` | 0.40 | 0.25 | 0.20 | 0.15 | 0.00 |
| Todos os sinais | `tem_feedback and tem_reputacao and tem_youtube` | 0.35 | 0.20 | 0.15 | 0.20 | 0.10 |

Recalculado (`state['signal_weights'] = calculate_dynamic_weights(state)`)
sempre que:
- um feedback é registrado (`record_feedback`);
- `/sincronia` atualiza o `youtube_interest_vector`;
- o briefing matinal sincroniza o YouTube automaticamente (uma vez por dia).

> Nota: a checagem em `calculate_dynamic_weights` é sequencial
> (`elif`), então a combinação exata "feedback + youtube sem reputação"
> não tem uma linha própria — cai no estágio "Reputação + YouTube" apenas se
> `tem_reputacao` também for verdadeiro, ou no "Inicial"/"Feedback+Reputação"
> conforme o caso. Na prática, como `update_source_reputation` é chamado a
> cada feedback, `tem_reputacao` tende a ficar verdadeiro rapidamente.

## Progressão típica de aprendizado

1. **Dia 1** (estado inicial, `adaptive_state.json` recém-criado): pesos
   `{llm: 0.70, recency: 0.30}`. Score final ≈ score do Gemini, levemente
   ajustado pela recência.
2. **Após ~3 itens avaliados pelo Gemini**: `source_reputation` já tem
   entradas, mas `tem_reputacao` só vira `True` com `>=3` fontes —
   pesos passam a `{llm: 0.55, reputation: 0.25, recency: 0.20}`.
3. **Após 5+ feedbacks 👍/👎**: `tem_feedback=True` →
   `{llm: 0.40, reputation: 0.25, recency: 0.20, feedback: 0.15}`.
4. **Após `/sincronia` mapear 3+ interesses do YouTube**: se também houver
   feedback e reputação, pesos finais
   `{llm: 0.35, reputation: 0.20, recency: 0.15, feedback: 0.20, youtube: 0.10}`
   — `format_learning_status` mostra "(TODOS ATIVOS)" quando reputação,
   feedback e youtube têm peso > 0 simultaneamente.

## Graceful degradation

- Todas as funções de cálculo (`_calc_recency`, `_calc_feedback_score`,
  `_calc_youtube_alignment`) retornam valores neutros (5.0) quando faltam
  dados, então o score nunca "quebra" por ausência de histórico.
- `compute_adaptive_score` usa `weights.get(..., default)` — se
  `signal_weights` estiver incompleto, usa `{llm: 0.70, recency: 0.30}` como
  base.
- `load_state()` faz backfill de chaves ausentes a partir de
  `DEFAULT_STATE` (compatibilidade com arquivos antigos).
- `filter_and_score_items` envolve o recálculo adaptativo em `try/except`
  (log em `debug`) — se `adaptive_engine` falhar, o score do Gemini é usado
  sem alteração.
- `sync_youtube_signals` retorna `{}` em qualquer falha (sem credenciais,
  erro de API, falha do Gemini) — o vetor de interesses simplesmente não é
  atualizado.

## Feedback do Telegram (👍/👎)

Cada card enviado (`_send_items`, `send_morning_briefing`) inclui
`_build_feedback_keyboard(item)`:

```python
InlineKeyboardMarkup([[
    InlineKeyboardButton('👍 Relevante', callback_data=f'fb:+1:{h}:{src_short}:{sid_short}:{score}'),
    InlineKeyboardButton('👎 Não curto', callback_data=f'fb:-1:{h}:{src_short}:{sid_short}:{score}'),
]])
```

`callback_feedback` extrai `(feedback, item_hash_short, src_short,
sid_short, gemini_score)` e chama:

```python
record_feedback(item_hash_short, src_short, sid_short, gemini_score, feedback)
```

`record_feedback`:
1. Acrescenta entrada a `feedback_history` (FIFO `MAX_FEEDBACK_HISTORY=500`).
2. Incrementa `total_feedback_given`.
3. `update_source_reputation(source_name, gemini_score, state)` — feedback
   também reforça a reputação da fonte usando o score que o Gemini deu
   originalmente.
4. Recalcula `signal_weights`.
5. Salva o estado.

## Sincronização com YouTube (`sync_youtube_signals`)

- Busca a playlist de "liked videos" (`relatedPlaylists.likes`) e, se
  disponível, o "watch history" (`relatedPlaylists.watchHistory`) via OAuth.
- Junta títulos + canais (até 30 itens) e pede ao Gemini um vetor de
  interesses JSON `{"catolicismo": 0.85, "tecnologia": 0.72, ...}` (valores
  0.0–1.0).
- Chamado em três lugares:
  - `send_morning_briefing` — uma vez por dia (`last_youtube_sync != hoje`).
  - `/sincronia` — sob demanda.
  - Resultado sempre atualiza `youtube_interest_vector`,
    `last_youtube_sync` e `signal_weights`.

## Análise semanal (`run_weekly_analysis`)

- Agendada para domingo 08:00 (`weekly_analysis_job`) e disponível sob
  demanda via `/analise`.
- Requer `len(feedback_history) >= 3` ou `source_reputation` não vazio;
  caso contrário retorna "Ainda sem dados suficientes para análise. Continue
  usando o bot!".
- Monta um prompt com: feedbacks positivos/negativos, top 5 melhores fontes,
  top 3 piores fontes, top 5 comandos mais usados e os pesos atuais; pede ao
  Gemini um relatório de até 10 linhas com (1) o que o usuário mais gosta,
  (2) o que deve ser reduzido, (3) uma sugestão de ajuste automático.
- Salva `last_auto_analysis` (timestamp) e acrescenta
  `{"date": ..., "report_preview": report[:100]}` a
  `auto_adjustments_log` (FIFO `MAX_ADJUSTMENTS_LOG=20`).
- **Importante**: o relatório é apenas informativo — `run_weekly_analysis`
  não aplica ajustes automaticamente nos pesos ou no perfil; é uma sugestão
  textual para o usuário (ou para uma futura automação).

## Onde o recálculo acontece

`src/profile_filter.py: filter_and_score_items`, passo 4 — para **cada item**
que passou pela pontuação em lote do Gemini:

```python
adaptive_state = load_state()
for item in enriched:
    gemini_score = item.get('_score', 5)
    source_name = item.get('source_name', '')
    item['_score'] = compute_adaptive_score(item, gemini_score, adaptive_state)
    if source_name:
        update_source_reputation(source_name, gemini_score, adaptive_state)
save_state(adaptive_state)
```

Ou seja, **toda vez que um item é avaliado** (em qualquer comando ou no
briefing), a reputação da fonte é atualizada com o score original do Gemini,
e o `_score` final exibido/usado para ordenação/filtro já é o score
adaptativo — não o score "puro" do Gemini.

## Comandos relacionados

Ver [COMMANDS.md](COMMANDS.md) para `/aprendizado`, `/analise`,
`/sincronia`, `/config`. Schema completo do estado em
[ai-context/STATE_SCHEMA.md](ai-context/STATE_SCHEMA.md).
