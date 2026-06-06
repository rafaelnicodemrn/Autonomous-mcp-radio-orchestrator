import asyncio
import json
import os
import random
import shutil
import sys

import requests
import edge_tts
from pydub import AudioSegment

MUSIC_DIR   = 'music'
CACHE_DIR   = os.path.join(MUSIC_DIR, 'cache', 'jamendo')
CATALOG_FILE = os.path.join(CACHE_DIR, 'catalog.json')
AUDIO_EXTS  = {'.mp3', '.m4a', '.ogg', '.wav', '.flac'}
JAMENDO_API = 'https://api.jamendo.com/v3.0/tracks/'


def fetch(source_config: dict, credentials=None) -> list[dict]:
    return []


# ── Local source ─────────────────────────────────────────────────────────────

def _available_tracks(extra_paths: list[str] | None = None) -> list[str]:
    dirs = []
    if os.path.exists(MUSIC_DIR):
        dirs.append(MUSIC_DIR)
    for p in (extra_paths or []):
        if os.path.isdir(p):
            dirs.append(p)
        else:
            print(f"  [musica-local] path não encontrado: {p}")

    result = []
    seen   = set()
    for base in dirs:
        for dirpath, _, filenames in os.walk(base):
            if base == MUSIC_DIR and CACHE_DIR.replace('\\', '/') in dirpath.replace('\\', '/'):
                continue
            for filename in filenames:
                if os.path.splitext(filename)[1].lower() in AUDIO_EXTS:
                    full = os.path.abspath(os.path.join(dirpath, filename))
                    if full not in seen:
                        seen.add(full)
                        result.append(full)
    return result


def _track_info_from_file(path: str) -> dict:
    title, artist, album = '', '', ''
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(path, easy=True)
        if audio:
            title  = str(audio.get('title',  [''])[0]).strip()
            artist = str(audio.get('artist', [''])[0]).strip()
            album  = str(audio.get('album',  [''])[0]).strip()
    except Exception:
        pass
    if not title and not artist:
        name = os.path.splitext(os.path.basename(path))[0]
        if ' - ' in name:
            parts = name.split(' - ', 1)
            artist, title = parts[0].strip(), parts[1].strip()
        else:
            title = name
    return {'path': path, 'title': title, 'artist': artist, 'album': album}


def _get_local_tracks(num_tracks: int, extra_paths: list[str] | None = None) -> list[dict]:
    available = _available_tracks(extra_paths)
    if not available:
        dirs = f"'{MUSIC_DIR}/'" + ''.join(f", '{p}'" for p in (extra_paths or []))
        raise FileNotFoundError(f"Nenhuma musica encontrada em {dirs}.")
    selected = random.sample(available, min(num_tracks, len(available)))
    return [_track_info_from_file(p) for p in selected]


# ── Jamendo source ────────────────────────────────────────────────────────────

def _load_catalog() -> dict:
    if os.path.exists(CATALOG_FILE):
        with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_catalog(catalog: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


def _fetch_from_api(client_id: str, tags: str, min_dur: int, max_dur: int, limit: int) -> list[dict]:
    params = {
        'client_id':             client_id,
        'format':                'json',
        'limit':                 min(limit, 200),
        'tags':                  tags,
        'audioformat':           'mp32',
        'audiodownload_allowed': 1,
        'order':                 'popularity_month',
    }
    if min_dur or max_dur:
        params['duration_between'] = f"{min_dur}_{max_dur}"

    resp = requests.get(JAMENDO_API, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get('headers', {}).get('status') != 'success':
        raise RuntimeError(data.get('headers', {}).get('error_message', 'Jamendo API error'))

    results = data.get('results', [])
    random.shuffle(results)  # variedade a cada execucao
    return results


def _download_track(track: dict) -> str | None:
    track_id = str(track['id'])
    path = os.path.join(CACHE_DIR, f"{track_id}.mp3")
    if os.path.exists(path):
        return path

    url = track.get('audiodownload') or track.get('audio')
    if not url:
        return None

    print(f"  Baixando: {track.get('name')} — {track.get('artist_name')}")
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=16384):
                f.write(chunk)
        return path
    except Exception as e:
        print(f"  [download] erro: {e}")
        if os.path.exists(path):
            os.remove(path)
        return None


def download_cache(source_config: dict) -> int:
    """Baixa faixas do Jamendo para o cache local. Retorna o número de novas faixas."""
    settings    = source_config.get('settings') or {}
    jamendo_cfg = settings.get('jamendo') or {}

    client_id = os.getenv(jamendo_cfg.get('api_key_env', 'JAMENDO_CLIENT_ID'), '')
    if not client_id:
        print("  [jamendo] JAMENDO_CLIENT_ID não configurado no .env")
        return 0

    tags    = jamendo_cfg.get('tags', 'lounge')
    min_dur = jamendo_cfg.get('min_duration', 60)
    max_dur = jamendo_cfg.get('max_duration', 360)
    limit   = min(settings.get('cache_size', 50), 200)

    catalog    = _load_catalog()
    downloaded = 0

    print(f"  Buscando até {limit} faixas no Jamendo (tags: {tags})...")
    try:
        api_tracks = _fetch_from_api(client_id, tags, min_dur, max_dur, limit)
        for track in api_tracks:
            tid  = str(track['id'])
            path = _download_track(track)
            if path:
                catalog[tid] = {
                    'title':  track.get('name', ''),
                    'artist': track.get('artist_name', ''),
                    'album':  track.get('album_name', ''),
                    'tags':   tags,
                    'file':   os.path.basename(path),
                }
                downloaded += 1
                _save_catalog(catalog)   # salva após cada faixa — seguro contra interrupções
    except Exception as e:
        print(f"  [jamendo] erro: {e}")

    return downloaded


def _get_jamendo_tracks(jamendo_cfg: dict, num_tracks: int) -> list[dict]:
    client_id = os.getenv(jamendo_cfg.get('api_key_env', 'JAMENDO_CLIENT_ID'), '')
    if not client_id:
        raise ValueError("JAMENDO_CLIENT_ID nao configurado no .env")

    tags    = jamendo_cfg.get('tags', 'lounge')
    min_dur = jamendo_cfg.get('min_duration', 60)
    max_dur = jamendo_cfg.get('max_duration', 360)

    catalog = _load_catalog()

    # Busca novas faixas na API
    fresh_ids = set()
    try:
        api_tracks = _fetch_from_api(client_id, tags, min_dur, max_dur, num_tracks * 3)
        for track in api_tracks:
            tid  = str(track['id'])
            path = _download_track(track)
            if path:
                catalog[tid] = {
                    'title':  track.get('name', ''),
                    'artist': track.get('artist_name', ''),
                    'album':  track.get('album_name', ''),
                    'tags':   tags,
                    'file':   os.path.basename(path),
                }
                fresh_ids.add(tid)
        _save_catalog(catalog)
    except Exception as e:
        print(f"  [jamendo] {e} — usando cache existente.")

    # Monta pool de faixas disponíveis em cache
    pool = []
    for tid, meta in catalog.items():
        fpath = os.path.join(CACHE_DIR, meta['file'])
        if os.path.exists(fpath):
            pool.append({'path': fpath, 'title': meta['title'],
                         'artist': meta['artist'], 'album': meta['album'],
                         '_fresh': tid in fresh_ids})

    if not pool:
        raise RuntimeError("Nenhuma faixa disponivel. Verifique JAMENDO_CLIENT_ID e conexao.")

    # Prioriza faixas recém-baixadas, completa com cache se necessário
    fresh  = [t for t in pool if t['_fresh']]
    cached = [t for t in pool if not t['_fresh']]
    random.shuffle(fresh)
    random.shuffle(cached)
    selected = (fresh + cached)[:num_tracks]

    return [{k: v for k, v in t.items() if k != '_fresh'} for t in selected]


# ── Common helpers ────────────────────────────────────────────────────────────

def _tts_label(track: dict) -> str:
    if track['artist']:
        return f"{track['title']} de {track['artist']}"
    return track['title']


def _display_label(track: dict) -> str:
    parts = [track['title']]
    if track['artist']:
        parts.append(track['artist'])
    if track['album']:
        parts.append(track['album'])
    return ' · '.join(filter(None, parts))


async def _tts(text: str, voice: str, path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


# ── Episode generator ─────────────────────────────────────────────────────────

def generate_episode(source_config: dict, output_dir: str,
                     narrators: list[dict], is_first_of_day: bool = False,
                     station_name: str = 'RadioIA') -> int:
    settings    = source_config.get('settings', {})
    num_tracks  = settings.get('num_tracks', 3)
    source      = settings.get('source', 'local')
    voice       = narrators[0]['voice'] if narrators else 'pt-BR-ThalitaMultilingualNeural'
    source_name = source_config.get('name', 'Selecao Musical')

    # Busca faixas conforme a fonte
    if source == 'jamendo':
        tracks = _get_jamendo_tracks(settings.get('jamendo', {}), num_tracks)
    else:
        tracks = _get_local_tracks(num_tracks, settings.get('paths', []))

    track_tts = ', '.join(_tts_label(t) for t in tracks)

    n = len(tracks)
    if is_first_of_day:
        preamble = f"Bom dia! Voce esta ouvindo a {station_name}. Vamos comecar o dia com musica."
    else:
        preamble = settings.get(
            'intro_text',
            f"E hora da {source_name}! Preparamos {n} faixa{'s' if n > 1 else ''} para voce."
        )
    intro_text = f"{preamble} A seguir: {track_tts}."

    outro_text = settings.get(
        'outro_text',
        "E assim encerramos nossa selecao musical. Voltamos logo com mais programacao."
    )

    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, 'temp')
    os.makedirs(temp_dir, exist_ok=True)

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    intro_path = os.path.join(temp_dir, 'intro.mp3')
    outro_path = os.path.join(temp_dir, 'outro.mp3')
    asyncio.run(_tts(intro_text, voice, intro_path))
    asyncio.run(_tts(outro_text, voice, outro_path))

    episode = AudioSegment.silent(400)
    episode += AudioSegment.from_mp3(intro_path)
    episode += AudioSegment.silent(1200)

    for track in tracks:
        episode += AudioSegment.from_file(track['path'])
        episode += AudioSegment.silent(600)
        print(f"  + {_display_label(track)}")

    episode += AudioSegment.from_mp3(outro_path)
    episode += AudioSegment.silent(400)

    episode_path = os.path.join(output_dir, 'episode.mp3')
    episode.export(episode_path, format='mp3', bitrate='128k',
                   tags={'title': source_name, 'artist': station_name})

    shutil.rmtree(temp_dir)
    duration = round(len(episode) / 1000)

    links = [
        {
            'title':   t['title'] or 'Faixa',
            'channel': t['artist'] or 'Desconhecido',
            'url':     '', 'views': 0, 'published_at': '',
            'top_comments': [], 'album': t['album'],
        }
        for t in tracks
    ]

    metadata = {
        'source_name':      source_name,
        'duration_seconds': duration,
        'videos_covered':   len(tracks),
        'links':            links,
    }
    with open(os.path.join(output_dir, 'episode.json'), 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return duration
