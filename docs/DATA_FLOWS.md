# Fluxos de Dados — RadioIA

Dois fluxos principais: o **briefing matinal automático** e um **comando
on-demand** (`/fe` como exemplo). Ambos convergem no mesmo pipeline de
enriquecimento/filtragem/envio.

## Fluxo 1 — Briefing matinal automático (07:00)

Disparado por `job_queue.run_daily(send_morning_briefing, time=dt_time(7, 0, 0))`
em `telegram_bot.py: main()`.

```
1. JobQueue dispara send_morning_briefing(context) às 07:00
        │
2. state = load_state()
   chat_id = state['chat_id']
   → se chat_id ausente: loga warning e ABORTA
        │
3. Sincronização YouTube (uma vez/dia)
   adaptive_state = load_adaptive_state()
   if adaptive_state['last_youtube_sync'] != hoje:
       creds = get_youtube_credentials()        (src/auth.py)
       if creds:
           yt = build('youtube','v3', credentials=creds)
           vector = sync_youtube_signals(yt)     (adaptive_engine)
           adaptive_state['youtube_interest_vector'] = vector
           adaptive_state['last_youtube_sync'] = hoje
           adaptive_state['signal_weights'] = calculate_dynamic_weights(adaptive_state)
           save_adaptive_state(adaptive_state)
        │
4. proc = _run_main_py(BRIEFING_SOURCES)
   # BRIEFING_SOURCES = [biblia, utilidades, catolicismo, noticias,
   #                      tecnologia, politica, conservadorismo]
   # python main.py biblia utilidades catolicismo noticias tecnologia politica conservadorismo
        │
5. send_briefing_header(bot, chat_id)
   → "☀️ Bom dia, Rafael! / RadioIA Pessoal · <data PT-BR> / ━━━━━━━━━━━━━━━━━━━━"
        │
6. items = await _wait_and_collect(proc, BRIEFING_SOURCES, timeout=600)
   # aguarda main.py terminar (até 10 min) e lê
   # output/<YYYY-MM-DD>/<hora>_<source_id>/episode.json para cada source_id
        │
   se items vazio → send_text("⚠️ Nenhum conteúdo gerado...") e ABORTA
        │
7. Agrupa items por source_id → by_source = {biblia: [...], noticias: [...], ...}
        │
8. Para cada (source_id, source_items):
        │
   8a. send_section_header(bot, chat_id, source_id)
       → "━━━━━━━━━━━━━━━━━━━━ / <CATEGORY_TITLES[source_id]>"
       ex: "📰 Notícias"
        │
   8b. enriched_list = [enrich_item(i) for i in source_items]
       # content_enricher.enrich_item:
       #  - translate_if_needed (se EN)
       #  - extract_image (og:image / thumbnail YouTube)
       #  - score_item (0-10, baseado em USER_KEYWORDS/TRUSTED_SOURCES/recência)
        │
   8c. enriched_list = deduplicate(enriched_list)
       # remove duplicatas por URL idêntica e por similaridade de título (>=0.55)
        │
   8d. enriched_list.sort(key=_score, reverse=True)
        │
   8e. for enriched in enriched_list[:max_items_per_category]:  # default 3
           keyboard = _build_feedback_keyboard(enriched)
           # fb:+1:<hash8>:<src10>:<sid8>:<score>  /  fb:-1:...
           send_item_card(bot, chat_id, enriched, enriched, reply_markup=keyboard)
           # HTML: emoji+fonte+estrelas / título linkado / bullets / link / hashtags
           # foto via og:image/thumbnail, fallback texto
        │
   ⚠️ NOTA: o briefing matinal NÃO chama filter_and_score_items
   (perfil/adaptive recalc) nem _apply_quotas — usa apenas
   score_item (content_enricher) + dedup + ordenação + corte por
   max_items_per_category. O recálculo adaptativo completo (passo 4 de
   filter_and_score_items) só ocorre nos comandos on-demand (Fluxo 2).
        │
9. state['last_briefing'] = now().isoformat(); save_state(state)
        │
10. send_text(bot, chat_id, "━━━━━━━━━━━━━━━━━━━━ / ☀️ Bom dia! Esse foi seu briefing matinal.")
```

### Saída no Telegram (exemplo)

```
☀️ Bom dia, Rafael!
RadioIA Pessoal · Sábado, 13 de junho de 2026
━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━
📖 Palavra do Dia

📖 Palavra do Dia  ⭐
📌 Salmos 23:1 — "O Senhor é o meu pastor; nada me faltará."
[👍 Relevante] [👎 Não curto]

━━━━━━━━━━━━━━━━━━━━
📰 Notícias

📰 G1  ⭐⭐
📌 [Governo anuncia novo pacote de medidas econômicas](https://...)
• Resumo gerado pelo Gemini em 1-2 frases...
🔗 Ler artigo completo
#noticias
[👍 Relevante] [👎 Não curto]

(... demais seções: utilidades, catolicismo, tecnologia, politica, conservadorismo)

━━━━━━━━━━━━━━━━━━━━
☀️ Bom dia! Esse foi seu briefing matinal.
```

## Fluxo 2 — Comando on-demand (`/fe`)

Disparado pelo usuário enviando `/fe` no Telegram.
`COMMANDS['/fe'] = ['biblia', 'catolicismo', 'conservadorismo']`,
`YOUTUBE_KEYWORDS['/fe'] = ['catolicismo reflexão', 'Padre Paulo Ricardo']`.

```
1. Update recebido → _make_command_handler(['biblia','catolicismo',
   'conservadorismo'], 'Fe', '/fe') → cmd_generate(update, context,
   sources, 'Fe', '/fe')
        │
2. chat_id = update.effective_chat.id
   state = load_state(); state['chat_id'] = chat_id; save_state(state)
   record_command_usage('/fe')
   # adaptive_state['command_usage']['/fe'] += 1
        │
3. reply_text("⏳ Gerando Fe...\nAguarde alguns minutos.")
        │
4. proc = _run_main_py(['biblia','catolicismo','conservadorismo'])
   # python main.py biblia catolicismo conservadorismo
   items = await _wait_and_collect(proc, sources, timeout=360)
   # lê output/<hoje>/*/episode.json para essas 3 source_ids
        │
5. yt_items = _fetch_youtube_for_cmd('/fe')
   # creds = get_youtube_credentials()
   # yt = build('youtube','v3', credentials=creds)
   # for kw in ['catolicismo reflexão', 'Padre Paulo Ricardo']:
   #     search_youtube_by_keyword(kw, yt, max_results=2)
   items.extend(yt_items)
        │
   se items vazio → reply_text("⚠️ Nenhum conteúdo encontrado para Fe...") e ABORTA
        │
6. reply_text("✅ Fe — N item(s) encontrado(s)")
        │
7. _send_items(bot, chat_id, items, '/fe')
```

### Dentro de `_send_items` (pipeline completo)

```
state = load_state()
sent_ids = set(state['sent_item_ids'])
max_items = state['config']['max_items_per_category']  # default 3

# 1. Enriquecimento
enriched_items = [enrich_item(i) for i in items]   # title/text traduzidos,
                                                    # _image_url, _score (heurístico)

# 2. Deduplicação + ordenação preliminar
enriched_items = deduplicate(enriched_items)
enriched_items.sort(key=_score, reverse=True)

# 3. Filtragem por perfil (telegram.perfil)
profile = load_profile()
enriched_items = filter_and_score_items(enriched_items, profile)
#   3.1 should_block — remove itens com palavras de ignorar_sempre
#   3.2 score_batch_with_gemini (lotes de 5, MODEL_FILTER=gemini-2.5-flash-lite)
#       → _score = score Gemini (0-10), _motivo
#   3.3 translate_if_needed se idioma_preferido=pt-BR e título em EN
#   3.4 RECÁLCULO ADAPTATIVO:
#       adaptive_state = load_adaptive_state()
#       for item in enriched:
#           gemini_score = item['_score']
#           item['_score'] = compute_adaptive_score(item, gemini_score, adaptive_state)
#           update_source_reputation(item['source_name'], gemini_score, adaptive_state)
#       save_adaptive_state(adaptive_state)
#   3.5 filtra _score >= score_minimo_enviar (default 5)
#   3.6 ordena por _score desc
#   3.7 diversity_guard(max_per_topic=2)  → limita copa/gremio/ia/papa/
#       politica_br/economia a 2 itens cada

# 4. Quotas do comando
enriched_items = _apply_quotas(enriched_items, '/fe')
# load_quotas('/fe') → telegram.quotas.fe = {max_por_fonte: 3, max_total: 8}

# 5. Envio
for enriched in enriched_items[:max_items*3]:   # até 9
    keyboard = _build_feedback_keyboard(enriched)
    send_item_card(bot, chat_id, enriched, enriched, reply_markup=keyboard)
    sent_ids.add(item_hash(enriched))
    if enriched.get('_audio_path') and not audio_sent:
        last_audio_path = enriched['_audio_path']

# 6. Botão de episódio completo (se houver mp3)
if last_audio_path existe:
    send_message("🎧 N item(s) enviado(s)",
                  reply_markup=[[ "🎵 Ouvir episódio completo" → play:<folder> ]])

# 7. Persistência
state['sent_item_ids'] = list(sent_ids)
save_state(state)
```

### Feedback do usuário (loop de aprendizado)

```
Usuário toca "👍 Relevante" em um card
        │
callback_feedback(update, context)
   query.data = "fb:+1:a1b2c3d4:PadrePauloR:catolici:8"
   parts → feedback='+1', item_hash_short='a1b2c3d4',
           src_short='PadrePauloR', sid_short='catolici', gemini_score=8
        │
record_feedback('a1b2c3d4', 'PadrePauloR', 'catolici', 8, '+1')
   → feedback_history.append({...})
   → update_source_reputation('PadrePauloR', 8, state)
   → state['signal_weights'] = calculate_dynamic_weights(state)
   → save_state(state)
        │
query.edit_message_reply_markup(reply_markup=None)  # remove botões
query.message.reply_text("👍 Obrigado pelo feedback! ...")
```

Esse feedback influencia:
- `source_reputation['PadrePauloR']['avg']` (sinal de reputação).
- `feedback_history` → `_calc_feedback_score` para futuros itens dessa
  fonte.
- `signal_weights` — se acumular 5+ feedbacks, o peso do sinal `feedback`
  passa a ser > 0 em `compute_adaptive_score`.

## Diferenças entre os dois fluxos

| Aspecto | Briefing matinal | Comando on-demand |
|---|---|---|
| Disparo | `JobQueue.run_daily` 07:00 | Usuário envia comando |
| Fontes extras do YouTube por keyword | Não | Sim (`_fetch_youtube_for_cmd`) |
| `filter_and_score_items` (perfil + Gemini batch + recálculo adaptativo) | **Não** | Sim |
| `_apply_quotas` | Não | Sim (`telegram.quotas`) |
| `diversity_guard` | Não | Sim (dentro de `filter_and_score_items`) |
| Agrupamento | Por seção (`source_id`), com cabeçalhos | Lista única, ordenada por score |
| Limite por seção | `max_items_per_category` (3) | `max_items_per_category * 3` (9), reduzido por quotas |
| Botão de episódio completo | Não | Sim, se `_audio_path` disponível |

> Observação para evolução futura: como o briefing matinal não passa pelo
> `filter_and_score_items`, ele não atualiza `source_reputation` nem aplica
> `score_minimo_enviar`/quotas — apenas os comandos on-demand alimentam o
> motor adaptativo via pontuação Gemini. O feedback 👍/👎 funciona em ambos
> os fluxos, pois `_build_feedback_keyboard` é usado nos dois.
