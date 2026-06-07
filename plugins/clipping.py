"""
Plugin RadioIA — Clipping de Mídia

Busca como diferentes veículos estão cobrindo um tema específico e gera
um episódio no estilo "o que a imprensa diz sobre X".

Uso:
  python main.py "clipping:queda de avião da empresa xyz"
  python main.py "clipping:eleições municipais 2026"

O tópico é sempre passado via CLI — o config.yaml define apenas os defaults.

Para usar, adicione ao config.yaml:
  - id: clipping
    type: clipping
    name: "Clipping"
    enabled: true
    settings:
      max_sources: 5        # máximo de veículos a incluir
      days_lookback: 1      # só artigos dos últimos N dias
      fetch_content: true   # extrai texto completo via trafilatura (recomendado)
      max_content_chars: 2000   # limite de caracteres por artigo
"""

import hashlib
import re
import urllib.parse
from datetime import date, timedelta

import feedparser
import trafilatura

GOOGLE_NEWS_RSS  = "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
MAX_CONTENT_CHARS = 2000
RSS_FETCH_LIMIT   = 20   # máximo de entradas a processar do RSS por query


def _pub_date(entry) -> date | None:
    try:
        import email.utils
        return email.utils.parsedate_to_datetime(entry.get('published', '')).date()
    except Exception:
        return None


def _source_name(entry) -> str:
    name = (entry.get('source') or {}).get('title', '')
    if name:
        return name
    # Fallback: extrai do título (padrão "Título - Veículo")
    title = entry.get('title', '')
    if ' - ' in title:
        return title.rsplit(' - ', 1)[-1].strip()
    return 'Fonte desconhecida'


def _fetch_content(url: str, max_chars: int) -> tuple[str, str]:
    """Retorna (título, texto) extraídos via trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return '', ''
        text  = trafilatura.extract(downloaded, include_comments=False,
                                    include_tables=False, no_fallback=False) or ''
        meta  = trafilatura.extract_metadata(downloaded)
        title = (meta.title if meta else '') or ''
        return title, text[:max_chars]
    except Exception:
        return '', ''


def _rss_summary(entry) -> str:
    raw = entry.get('summary', '')
    return re.sub(r'<[^>]+>', '', raw).strip()


def _build_query(topic: str, followup: bool, days_lookback: int) -> str:
    """Monta a query do Google News. Em modo followup, restringe a artigos recentes."""
    query = topic
    if followup:
        since = (date.today() - timedelta(days=max(1, days_lookback))).isoformat()
        query = f'{topic} after:{since}'
    return GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(query))


def _fetch_entries(url: str, since: date, max_entries: int,
                   seen_urls: set, fetch_full: bool, max_chars: int,
                   topic: str, source_config: dict) -> list[dict]:
    """Processa entradas do RSS e retorna items prontos (sem cap de max_sources)."""
    feed = feedparser.parse(url)
    items = []
    today = date.today().isoformat()

    for entry in feed.entries[:max_entries]:
        pub = _pub_date(entry)
        if pub and pub < since:
            continue

        entry_url = entry.get('link', '').strip()
        if not entry_url or entry_url in seen_urls:
            continue
        seen_urls.add(entry_url)

        source    = _source_name(entry)
        rss_title = entry.get('title', source)
        clean_title = rss_title
        if rss_title.endswith(f' - {source}'):
            clean_title = rss_title[: -(len(source) + 3)].strip()

        print(f'  [{source}] {clean_title[:65]}...' if len(clean_title) > 65 else f'  [{source}] {clean_title}')

        text  = ''
        title = clean_title
        if fetch_full:
            fetched_title, fetched_text = _fetch_content(entry_url, max_chars)
            if fetched_text:
                text = fetched_text
            if fetched_title:
                title = fetched_title
        if not text:
            text = _rss_summary(entry)
        if not text:
            continue

        uid = hashlib.md5(entry_url.encode()).hexdigest()[:8]
        items.append({
            'id':           f'clipping-{uid}-{today}',
            'title':        title,
            'url':          entry_url,
            'text':         text,
            'source_name':  source,
            'source_type':  source_config.get('type', 'clipping'),
            'published_at': pub.isoformat() if pub else today,
            'views':        0,
            'comments':     [],
            'channel':      topic,
        })

    return items


def fetch(source_config: dict, credentials=None) -> list[dict]:
    settings      = source_config.get('settings') or {}
    topic         = settings.get('topic', '').strip()
    days_lookback = int(settings.get('days_lookback', 1))
    fetch_full    = settings.get('fetch_content', True)
    max_chars     = int(settings.get('max_content_chars', MAX_CONTENT_CHARS))
    followup      = bool(settings.get('followup', False))

    if not topic:
        print('  [clipping] nenhum tópico informado. Use: python main.py "clipping:seu tópico"')
        return []

    mode = 'followup' if followup else 'primeira cobertura'
    print(f'  Buscando cobertura [{mode}]: "{topic}"')

    since    = date.today() - timedelta(days=days_lookback)
    seen_urls: set = set()

    url   = _build_query(topic, followup, days_lookback)
    items = _fetch_entries(url, since, RSS_FETCH_LIMIT, seen_urls,
                           fetch_full, max_chars, topic, source_config)

    print(f'  {len(items)} veículo(s) encontrado(s) sobre "{topic}".')
    return items
