"""
Podcast source — transcreve e resume episódios de podcast via RSS ou URL direta.

Parâmetros (settings em config.yaml):
  url                  — RSS feed ou URL direta do MP3/áudio
  max_items            — episódios a buscar do feed RSS (default: 1)
  days_lookback        — janela de busca no RSS em dias (default: 7)
  show_notes_min_chars — mínimo de chars nas show notes antes de usar Whisper (default: 500)
  whisper_start        — início do trecho a transcrever, em segundos (default: 0)
  whisper_duration     — duração do trecho a transcrever, em segundos (default: 600 = 10min)
  topic                — tema específico para focar no roteiro (opcional)
  whisper_model        — tamanho do modelo Whisper: tiny/base/small/medium/large (default: base)

Uso via CLI (sobrescreve settings):
  python main.py podcast:https://feeds.example.com/feed.rss
  python main.py podcast:url=https://...,start=300,duration=600,topic=inteligência artificial
  python main.py podcast-tech:start=120,topic=privacidade
"""

import os
import re
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone

import feedparser

SHOW_NOTES_MIN_CHARS = 500
WHISPER_START_DEFAULT = 0
WHISPER_DURATION_DEFAULT = 600
WHISPER_MODEL_DEFAULT = 'base'
MAX_CONTENT_CHARS = 6000


def _is_audio_url(url: str) -> bool:
    clean = url.split('?')[0].lower()
    return any(clean.endswith(ext) for ext in ('.mp3', '.m4a', '.ogg', '.wav', '.flac', '.opus'))


def _extract_enclosure(entry) -> str:
    for link in entry.get('enclosures', []):
        href = link.get('href') or link.get('url', '')
        if href:
            return href
    return entry.get('link', '')


def _clean_html(text: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _get_show_notes(entry) -> str:
    for content in entry.get('content', []):
        if content.get('value'):
            return _clean_html(content['value'])
    raw = entry.get('summary', '') or entry.get('description', '')
    return _clean_html(raw)


def _download_partial(audio_url: str, start_sec: int, duration_sec: int, out_path: str) -> bool:
    """Baixa o áudio e recorta o trecho com pydub. Retorna True se gerou o arquivo."""
    try:
        from pydub import AudioSegment
    except ImportError:
        print('    [aviso] pydub não instalado. pip install pydub')
        return False

    print(f'    Baixando áudio do podcast...')
    full_tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            full_tmp = f.name
        urllib.request.urlretrieve(audio_url, full_tmp)

        audio = AudioSegment.from_file(full_tmp)
        start_ms = start_sec * 1000
        end_ms = (start_sec + duration_sec) * 1000
        clip = audio[start_ms : min(end_ms, len(audio))]
        clip.export(out_path, format='mp3', bitrate='64k')

        actual = len(clip) / 1000
        print(f'    Trecho: {start_sec}s – {start_sec + int(actual)}s ({actual:.0f}s)')
        return True
    except Exception as e:
        print(f'    [aviso] Falha ao processar áudio: {e}')
        return False
    finally:
        if full_tmp:
            try:
                os.unlink(full_tmp)
            except OSError:
                pass


def _transcribe(audio_path: str, model_name: str) -> str:
    try:
        import whisper
    except ImportError:
        print('    [aviso] whisper não instalado. pip install openai-whisper')
        return ''

    try:
        print(f'    Transcrevendo com Whisper ({model_name})...')
        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path, language='pt', fp16=False)
        text = result.get('text', '').strip()
        print(f'    Transcrição: {len(text)} chars')
        return text[:MAX_CONTENT_CHARS]
    except Exception as e:
        print(f'    [aviso] Falha na transcrição: {e}')
        return ''


def _get_content(audio_url: str, show_notes: str, settings: dict) -> str:
    """Estratégia híbrida: show notes se suficientes, senão Whisper no trecho configurado."""
    min_chars = int(settings.get('show_notes_min_chars', SHOW_NOTES_MIN_CHARS))

    if len(show_notes) >= min_chars:
        print(f'    Show notes suficientes ({len(show_notes)} chars) — sem transcrição.')
        return show_notes[:MAX_CONTENT_CHARS]

    if not audio_url:
        print(f'    Show notes insuficientes e sem URL de áudio — usando o que há.')
        return show_notes

    start    = int(settings.get('whisper_start', WHISPER_START_DEFAULT))
    duration = int(settings.get('whisper_duration', WHISPER_DURATION_DEFAULT))
    model    = settings.get('whisper_model', WHISPER_MODEL_DEFAULT)

    print(f'    Show notes curtas ({len(show_notes)} chars) — usando Whisper...')

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if _download_partial(audio_url, start, duration, tmp_path):
            transcript = _transcribe(tmp_path, model)
            if transcript:
                if show_notes:
                    return f'[Show notes]\n{show_notes}\n\n[Transcrição]\n{transcript}'
                return transcript
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return show_notes


def _parse_param(param: str) -> dict:
    """
    Parseia o parâmetro CLI.
    - URL pura:               podcast:https://feeds.example.com/feed.rss
    - Chave=valor:            podcast:url=https://...,start=300,duration=600,topic=IA
    - Misto (só source_id):   podcast-tech:start=120,topic=privacidade
    """
    if not param:
        return {}
    if '=' not in param:
        return {'url': param}

    result = {}
    # Divide em pares chave=valor respeitando que valores podem ter '=' (URLs)
    for part in re.split(r',(?=[a-z_]+=)', param):
        k, _, v = part.partition('=')
        result[k.strip()] = v.strip()

    # Atalhos de nomenclatura
    if 'start' in result:
        result['whisper_start'] = result.pop('start')
    if 'duration' in result:
        result['whisper_duration'] = result.pop('duration')
    if 'model' in result:
        result['whisper_model'] = result.pop('model')

    return result


def _range_label(settings: dict) -> str:
    start    = int(settings.get('whisper_start', WHISPER_START_DEFAULT))
    duration = int(settings.get('whisper_duration', WHISPER_DURATION_DEFAULT))
    s_min, e_min = start // 60, (start + duration) // 60
    return f'{s_min}-{e_min} min' if start else f'primeiros {e_min} min'


def fetch(source_config: dict, credentials=None) -> list[dict]:
    settings = dict(source_config.get('settings') or {})

    # Injeta overrides do CLI (_param é injetado pelo main.py)
    cli_param = source_config.get('_param')
    if cli_param:
        settings.update(_parse_param(cli_param))

    url           = settings.get('url', '')
    topic         = settings.get('topic', '')
    max_items     = int(settings.get('max_items', 1))
    days_lookback = int(settings.get('days_lookback', 7))

    if not url:
        print('  [podcast] Nenhuma URL configurada em settings.url')
        return []

    items = []

    if _is_audio_url(url):
        # URL direta do arquivo de áudio
        title = os.path.basename(url.split('?')[0]) or 'Episódio'
        print(f'  [podcast] {title[:70]}')
        content = _get_content(url, '', settings)
        if content:
            items.append(_make_item(title, url, url, content, source_config, topic, settings))
    else:
        # RSS feed
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback)
        feed = feedparser.parse(url)
        podcast_name = feed.feed.get('title', source_config.get('name', 'Podcast'))

        count = 0
        for entry in feed.entries:
            if count >= max_items:
                break

            pub_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
            if pub_parsed:
                pub_dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            title     = entry.get('title', '').strip()
            audio_url = _extract_enclosure(entry)
            notes     = _get_show_notes(entry)
            ep_url    = entry.get('link', audio_url or url)

            print(f'  [{podcast_name}] {title[:70]}')
            content = _get_content(audio_url, notes, settings)

            if content:
                items.append(_make_item(title, ep_url, audio_url, content,
                                        source_config, topic, settings,
                                        channel=podcast_name, pub_parsed=pub_parsed))
                count += 1

    return items


def _make_item(title: str, url: str, audio_url: str, content: str,
               source_config: dict, topic: str, settings: dict,
               channel: str = '', pub_parsed=None) -> dict:
    source_name = source_config.get('name', channel or 'Podcast')
    pub_dt = (datetime(*pub_parsed[:6], tzinfo=timezone.utc)
              if pub_parsed else datetime.now(timezone.utc))

    return {
        'id':            audio_url or url,
        'title':         title,
        'url':           url,
        'text':          content,
        'source_name':   source_name,
        'source_type':   'podcast',
        'published_at':  pub_dt.isoformat(),
        'channel':       channel or source_name,
        'views':         0,
        'comments':      [],
        'topic':         topic,
        'range_label':   _range_label(settings),
    }
