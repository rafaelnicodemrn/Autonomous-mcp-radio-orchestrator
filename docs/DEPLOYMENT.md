# Deploy e Atualização — RadioIA

O projeto roda como **3 processos independentes** (ver `start_all.bat`,
usado no Windows local):

| Processo | Comando | Função |
|---|---|---|
| Player Web | `python serve.py` | Interface web para ouvir episódios (porta 5000) |
| Scheduler | `python scheduler.py` | Gera episódios conforme `config.yaml: schedule:` |
| Telegram Bot | `python telegram_bot.py` | Bot `@radiobootbot` — comandos, briefing, aprendizado |

Em produção (Google Cloud VM), cada processo deve rodar como um serviço
`systemd` independente, para reiniciar automaticamente em caso de falha ou
reboot.

## Pré-requisitos na VM

- VM Linux (ex: Ubuntu 22.04, instância `e2-micro` no Google Cloud — nível
  gratuito é suficiente para esta carga de trabalho).
- Python 3.11 e `venv`.
- Git (para clonar/atualizar o repositório).
- Acesso de saída à internet (RSS, APIs do YouTube/Gemini/TMDB/etc.).
- Arquivo `.env` configurado (baseado em `.env.example`) com todas as chaves
  necessárias — ver [CONFIG_GUIDE.md](CONFIG_GUIDE.md#variáveis-de-ambiente-env).
- Credenciais do Google Cloud TTS (`google-tts-credentials.json`, referenciado
  por `GOOGLE_APPLICATION_CREDENTIALS`).
- (Opcional) `credentials.json` + `token.json` para OAuth do YouTube — sem
  eles, `/sincronia` e a busca por inscrições ficam desabilitados, mas o
  restante do bot funciona normalmente (graceful degradation).

## Setup inicial

```bash
# 1. Clonar o repositório
git clone <url-do-repo> radioIA
cd radioIA

# 2. Criar e ativar o virtualenv
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
cp .env.example .env
nano .env   # preencher TELEGRAM_BOT_TOKEN, YOUTUBE_API_KEY, ANTHROPIC_API_KEY, etc.

# 5. Colocar credenciais do Google Cloud TTS
#    (copiar google-tts-credentials.json para a VM e apontar
#     GOOGLE_APPLICATION_CREDENTIALS no .env para o caminho absoluto)

# 6. Teste manual rápido
python telegram_bot.py
# Ctrl+C após confirmar que conecta sem erros, registrar /start no Telegram
```

## Serviços systemd

Crie um arquivo de unidade por processo em `/etc/systemd/system/`.

### `/etc/systemd/system/radioia-bot.service`
```ini
[Unit]
Description=RadioIA - Telegram Bot
After=network-online.target

[Service]
Type=simple
User=radioia
WorkingDirectory=/home/radioia/radioIA
EnvironmentFile=/home/radioia/radioIA/.env
ExecStart=/home/radioia/radioIA/.venv/bin/python telegram_bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/radioia-scheduler.service`
```ini
[Unit]
Description=RadioIA - Scheduler (grade de geração)
After=network-online.target

[Service]
Type=simple
User=radioia
WorkingDirectory=/home/radioia/radioIA
EnvironmentFile=/home/radioia/radioIA/.env
ExecStart=/home/radioia/radioIA/.venv/bin/python scheduler.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/radioia-serve.service`
```ini
[Unit]
Description=RadioIA - Player Web
After=network-online.target

[Service]
Type=simple
User=radioia
WorkingDirectory=/home/radioia/radioIA
EnvironmentFile=/home/radioia/radioIA/.env
ExecStart=/home/radioia/radioIA/.venv/bin/python serve.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Ativar e iniciar

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now radioia-bot radioia-scheduler radioia-serve
sudo systemctl status radioia-bot
```

## Logs

```bash
# Logs do bot em tempo real
journalctl -u radioia-bot -f

# Últimas 100 linhas do scheduler
journalctl -u radioia-scheduler -n 100 --no-pager
```

`telegram_bot.py` usa `logging.basicConfig(format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', level=logging.INFO)` — todos os logs (incluindo
erros de `_send_items`, `enrich_item`, sincronização do YouTube etc.) vão
para stdout/stderr, capturados pelo `journalctl`.

## Atualizando o projeto (deploy de novas versões)

```bash
cd /home/radioia/radioIA

# 1. Parar os serviços (evita conflito de escrita em config.yaml/*.json
#    durante o git pull)
sudo systemctl stop radioia-bot radioia-scheduler radioia-serve

# 2. Atualizar o código
git pull origin main

# 3. Atualizar dependências, se requirements.txt mudou
source .venv/bin/activate
pip install -r requirements.txt

# 4. Reiniciar os serviços
sudo systemctl start radioia-bot radioia-scheduler radioia-serve

# 5. Verificar status
sudo systemctl status radioia-bot radioia-scheduler radioia-serve
journalctl -u radioia-bot -n 30 --no-pager
```

### Cuidados com arquivos de estado

`config.yaml`, `adaptive_state.json` e `telegram_state.json` são
modificados em runtime (perfil, quotas, feedback, reputação de fontes,
histórico de envios). **Não sobrescreva esses arquivos com versões do
repositório** ao fazer deploy — eles não devem fazer parte do `git pull` se
o repositório os versiona como template. Se necessário, adicione-os ao
`.gitignore` no servidor de produção e mantenha apenas backups periódicos:

```bash
# Backup simples antes de cada deploy
cp config.yaml adaptive_state.json telegram_state.json /home/radioia/backups/$(date +%F)/
```

### Credenciais sensíveis (nunca commitar)

- `.env`
- `credentials.json`, `token.json` (OAuth YouTube)
- `google-tts-credentials.json`
- `adaptive_state.json` / `telegram_state.json` (dados pessoais de uso)

Confirme que essas entradas estão em `.gitignore`/`.claudeignore` antes de
qualquer `git push`.

## Verificação pós-deploy

1. `journalctl -u radioia-bot -n 50` — sem `Traceback` ou
   `TELEGRAM_BOT_TOKEN não configurado`.
2. No Telegram, enviar `/status` — deve responder com chat_id, último
   briefing e próximo horário.
3. Enviar `/config` — confirma que `config.yaml` foi lido corretamente
   (quotas e pesos aparecem).
4. Aguardar o próximo horário de `schedule:` (ou rodar manualmente
   `python main.py <fontes>`) e confirmar que `output/<data>/` é populado.
