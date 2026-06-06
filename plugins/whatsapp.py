"""
Plugin RadioIA — WhatsApp (Exportação Manual)

Lê exportações de grupos do WhatsApp (.zip contendo .txt) e gera episódios
com um resumo das mensagens do período configurado.

Como exportar:
  WhatsApp → Grupo → ⋮ → Mais → Exportar conversa → Sem mídia
  Salve o .zip na pasta configurada em 'path'.

Para usar, adicione ao config.yaml:
  - id: grupo-trabalho
    type: whatsapp
    name: "Grupo do Trabalho"
    enabled: true
    settings:
      path: "/caminho/para/exportacao.zip"   # arquivo .zip ou pasta com vários .zips
      days_lookback: 1                        # quantos dias incluir (padrão: 1)
      max_messages: 150                       # limite de mensagens enviadas ao LLM
      ignore_media: true                      # ignora linhas de mídia (foto, vídeo, áudio)

Suporta os formatos Android e iOS em português brasileiro.
"""

import os
import re
import zipfile
from datetime import date, timedelta

# ── Regex para os dois formatos de exportação ─────────────────────────────────
# Android: "27/05/2025 14:30 - Nome: mensagem"
_RE_ANDROID = re.compile(
    r'^(\d{1,2}/\d{1,2}/\d{4})\s+\d{2}:\d{2}\s+-\s+([^:]+?):\s+(.+)$'
)
# iOS: "[27/05/2025, 14:30:45] Nome: mensagem"  (com ou sem vírgula/segundos)
_RE_IOS = re.compile(
    r'^\[(\d{1,2}/\d{1,2}/\d{4}),?\s+\d{2}:\d{2}(?::\d{2})?\]\s+([^:]+?):\s+(.+)$'
)

_PATTERNS = [_RE_ANDROID, _RE_IOS]

# Mensagens de mídia e sistema a ignorar
_MEDIA_RE = re.compile(
    r'<.+omitid[ao]>|imagem omitida|vídeo omitido|áudio omitido|figurinha omitida|'
    r'sticker omitido|contato omitido|localização omitida|GIF omitido',
    re.IGNORECASE
)


def _find_zip(path: str) -> str | None:
    if os.path.isfile(path) and path.lower().endswith('.zip'):
        return path
    if os.path.isdir(path):
        zips = [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith('.zip')]
        return max(zips, key=os.path.getmtime) if zips else None
    return None


def _read_txt_from_zip(zip_path: str) -> str | None:
    with zipfile.ZipFile(zip_path, 'r') as z:
        txts = [n for n in z.namelist() if n.lower().endswith('.txt')]
        if not txts:
            return None
        name = max(txts, key=lambda n: z.getinfo(n).file_size)
        return z.read(name).decode('utf-8', errors='replace')


def _parse_date(date_str: str) -> date | None:
    try:
        parts = date_str.split('/')
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        return date(y, m, d)
    except Exception:
        return None


def _parse_messages(text: str, since: date) -> list[dict]:
    messages = []
    current  = None

    for line in text.splitlines():
        matched = False
        for pattern in _PATTERNS:
            m = pattern.match(line)
            if m:
                msg_date = _parse_date(m.group(1))
                if msg_date and msg_date >= since:
                    current = {
                        'date':   msg_date,
                        'sender': m.group(2).strip(),
                        'text':   m.group(3).strip(),
                    }
                    messages.append(current)
                else:
                    current = None
                matched = True
                break

        # Continuação de mensagem multi-linha
        if not matched and current is not None and line.strip():
            current['text'] += ' ' + line.strip()

    return messages


def fetch(source_config: dict, credentials=None) -> list[dict]:
    settings      = source_config.get('settings') or {}
    path          = settings.get('path', '').strip()
    days_lookback = int(settings.get('days_lookback', 1))
    max_messages  = int(settings.get('max_messages', 150))
    ignore_media  = settings.get('ignore_media', True)

    if not path:
        print("  [whatsapp] 'path' não configurado nas settings.")
        return []

    zip_path = _find_zip(path)
    if not zip_path:
        print(f"  [whatsapp] nenhum .zip encontrado em: {path}")
        return []

    print(f"  Lendo: {os.path.basename(zip_path)}")

    try:
        txt = _read_txt_from_zip(zip_path)
    except Exception as e:
        print(f"  [whatsapp] erro ao ler zip: {e}")
        return []

    if not txt:
        print("  [whatsapp] nenhum arquivo .txt encontrado no zip.")
        return []

    since    = date.today() - timedelta(days=days_lookback)
    messages = _parse_messages(txt, since)

    if ignore_media:
        messages = [m for m in messages if not _MEDIA_RE.search(m['text'])]

    if not messages:
        print(f"  [whatsapp] nenhuma mensagem nos últimos {days_lookback} dia(s).")
        return []

    # Limita ao máximo configurado (últimas N mensagens do período)
    messages = messages[-max_messages:]
    print(f"  {len(messages)} mensagem(ns) de {since.isoformat()} até hoje.")

    content = '\n'.join(f"{m['sender']}: {m['text']}" for m in messages)
    today   = date.today().isoformat()
    uid     = abs(hash(zip_path + today)) % 10**8

    return [{
        'id':           f"whatsapp-{uid}-{today}",
        'title':        source_config.get('name', 'WhatsApp'),
        'url':          '',
        'text':         content,
        'source_name':  source_config.get('name', 'WhatsApp'),
        'source_type':  source_config.get('type', 'whatsapp'),
        'published_at': today,
        'views':        0,
        'comments':     [],
        'channel':      'WhatsApp',
    }]
