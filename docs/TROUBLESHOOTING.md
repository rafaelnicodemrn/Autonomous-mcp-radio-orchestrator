# Troubleshooting — RadioIA

Problemas comuns, como identificá-los nos logs e como resolver.

## Bot não inicia: `TELEGRAM_BOT_TOKEN não configurado`

`telegram_bot.py: main()` verifica `TELEGRAM_BOT_TOKEN` no `.env` antes de
montar a aplicação. Se a variável estiver ausente ou vazia, o processo loga
o erro e termina imediatamente (sem subir o `Application`/`JobQueue`).

**Fix**: confirmar que `.env` existe (copiado de `.env.example`) e contém
`TELEGRAM_BOT_TOKEN=<token do @BotFather>`. Reiniciar o processo
(`radioia-bot` no systemd, ou a janela `RadioIA Telegram` no Windows).

## Briefing matinal não chega / `chat_id ausente`

`send_morning_briefing` lê `state['chat_id']` de `telegram_state.json`. Se
for `None` (bot nunca recebeu `/start`), a função loga um warning e aborta
sem enviar nada — sem erro visível no Telegram.

**Fix**: enviar `/start` para o bot pelo menos uma vez. Isso grava
`chat_id` em `telegram_state.json` (e também em `TELEGRAM_CHAT_ID` no
`.env`). Confirmar com `/status` que o `chat_id` está preenchido.

## `/sincronia` ou sync automático do YouTube não funcionam

`get_youtube_credentials()` (`src/auth.py`) retorna `None` se
`credentials.json`/`token.json` não existirem ou o token OAuth tiver
expirado sem refresh token válido. Nesse caso:

- `/sincronia` responde "⚠️ Credenciais do YouTube não configuradas."
- A sincronização automática no briefing (`sync_youtube_signals`) é
  simplesmente pulada — `youtube_interest_vector` não é atualizado, mas o
  restante do briefing prossegue normalmente (graceful degradation, ver
  [ADAPTIVE_SYSTEM.md](ADAPTIVE_SYSTEM.md#graceful-degradation)).

**Fix**: gerar `credentials.json` (OAuth client do Google Cloud Console,
tipo "Desktop app", com a YouTube Data API v3 habilitada) e rodar o fluxo de
autorização local para gerar `token.json`. Sem isso, o sistema funciona, mas
o sinal `youtube` do motor adaptativo permanece neutro/zerado.

## Erros do Gemini (timeout, rate limit, resposta inválida)

Chamadas ao Gemini passam por `_gemini_call_with_retry`: até 3 tentativas,
backoff entre 2s e 8s, timeout de 15s por chamada, `reraise=False` — em
caso de falha persistente, a função retorna `None`/valor neutro em vez de
propagar a exceção.

**Sintomas**: itens sem resumo/tradução, ou `_score` neutro (5) em vez do
score real do Gemini, em `score_batch_with_gemini`
(`src/profile_filter.py`).

**Fix**: normalmente se resolve sozinho na próxima execução. Se persistir,
verificar `ANTHROPIC_API_KEY`/chave do Gemini no `.env` e cota da API.

## `main.py` demora demais / processo é encerrado por timeout

`_run_main_py` + `_wait_and_collect` em `telegram_bot.py` aguardam o
subprocesso `python main.py <fontes...>` com timeout configurável:

| Contexto | Timeout |
|---|---|
| `_wait_and_collect` (uso genérico) | 300s |
| Comandos `/fe`, `/tech`, `/noticias`, etc. (`cmd_generate`) | 360s |
| Briefing matinal (`send_morning_briefing`) | 600s |

Se o timeout é atingido, o processo é **encerrado (`kill`)** e os itens já
gerados até esse ponto (pastas `output/<data>/<hora>_<source_id>/` com
`episode.json` já escrito) ainda são coletados — fontes que não terminaram
a tempo simplesmente não aparecem no resultado.

**Sintomas**: "✅ ... — N item(s) encontrado(s)" com N menor que o esperado,
ou "⚠️ Nenhum conteúdo encontrado" se nenhuma fonte terminou a tempo.

**Fix**: reduzir o número de fontes no comando, ou os `max_items_*`/
`max_videos_*` em `config.yaml: sources:` para fontes lentas (ex.
`youtube`, que baixa/transcreve vídeos). Verificar conectividade de rede da
VM/máquina.

## `UnicodeEncodeError` com emojis no console do Windows

Ao rodar scripts diretamente via `python -c "..."` (ou qualquer script que
imprima emojis) no `cmd.exe`/PowerShell padrão do Windows, o console usa o
codec `cp1252`, que não suporta caracteres como 🧠:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f9e0'
  in position ...: character maps to <undefined>
```

Isso **não afeta** o bot em produção — o Telegram recebe UTF-8 normalmente
via API HTTP, e logs gravados em arquivo/`journalctl` também não têm esse
problema. O erro só aparece ao imprimir emojis diretamente no console do
Windows.

**Fix** (para testes manuais/scripts ad-hoc):
- Rodar `chcp 65001` antes do comando para mudar o console para UTF-8, ou
- Definir `PYTHONIOENCODING=utf-8` no ambiente, ou
- Evitar `print()` com emoji em scripts de teste — usar `logging` ou
  redirecionar para arquivo (`> out.txt`).

## `config.yaml` corrompe acentos/emojis ao salvar

Edições programáticas de `config.yaml` (ex.: `/perfil add interesse ...`)
usam `yaml.safe_load` para ler e devem usar
`yaml.dump(..., allow_unicode=True, sort_keys=False)` para escrever, com o
arquivo aberto em modo `utf-8`. Se algum código usar `yaml.dump` sem
`allow_unicode=True`, acentos (ã, ç, é) e emojis em `config.yaml` são
gravados como sequências `\uXXXX` escapadas — ainda válido, mas difícil de
editar manualmente.

**Fix**: ao editar `config.yaml` programaticamente, sempre usar
`encoding="utf-8"` na abertura do arquivo e `allow_unicode=True` no
`yaml.dump`. Se o arquivo já foi corrompido (`\uXXXX` literais), basta
recarregá-lo com `yaml.safe_load` e salvá-lo novamente com as opções
corretas — o YAML é semanticamente equivalente, apenas a representação
muda.

## Botão de feedback (👍/👎) não responde / callback expira

`callback_data` do Telegram tem limite de **64 bytes UTF-8**.
`_build_feedback_keyboard` usa hashes/IDs curtos
(`fb:+1:<hash8>:<src10>:<sid8>:<score>`, ~30-36 bytes) justamente para ficar
dentro do limite. Se esse formato for alterado para incluir strings maiores
(ex. nome completo da fonte, título do item), o Telegram rejeita o teclado
silenciosamente ou o botão não responde.

**Fix**: ao modificar `_build_feedback_keyboard`/`callback_feedback`, manter
os campos curtos (hashes/prefixos truncados) e validar
`len(callback_data.encode('utf-8')) <= 64`.

## Quotas/score mínimo deixam comandos "vazios"

Se `/tech`, `/fe`, etc. retornam "✅ ... — 0 item(s)" mesmo com `main.py`
gerando itens, verificar:

1. `telegram.perfil.score_minimo_enviar` — itens com `_score` adaptativo
   abaixo desse valor são descartados em `filter_and_score_items` (passo
   3.5). Ver [ADAPTIVE_SYSTEM.md](ADAPTIVE_SYSTEM.md).
2. `telegram.perfil.ignorar_sempre` — itens cujo título/fonte contém algum
   termo dessa lista são bloqueados antes mesmo de chegar ao Gemini
   (`should_block`).
3. `telegram.quotas.<comando>` — `max_por_fonte`/`max_total` muito baixos
   podem zerar a lista após a deduplicação por fonte.

**Fix**: `/perfil` para inspecionar/ajustar `score_minimo_enviar` e
`ignorar_sempre`; `/config` para ver as quotas atuais. Reduzir
temporariamente `score_minimo_enviar` para depurar se o problema é de
filtragem.

## Episódio sem áudio (`episode.mp3` ausente)

Se um item aparece no Telegram mas o botão "🎵 Ouvir episódio completo" não
aparece, o `episode.json` correspondente não tem `_audio_path` válido — o
TTS pode ter falhado (`google-tts-credentials.json` ausente/inválido,
`GOOGLE_APPLICATION_CREDENTIALS` apontando para caminho errado, ou cota da
API do Google Cloud TTS excedida).

**Fix**: verificar `GOOGLE_APPLICATION_CREDENTIALS` no `.env` e que o
arquivo de credenciais existe e tem permissão de leitura. Checar logs de
`main.py` para erros do `texttospeech` client.
