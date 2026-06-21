"""
Plugin RadioIA — Passagens Bíblicas (ABíbliaDigital)

Busca passagens bíblicas via API abibliadigital.com.br e gera
episódios de reflexão e meditação.

Para usar, adicione ao config.yaml:
  - id: biblia
    type: biblia
    name: "Palavra do Dia"
    enabled: true
    settings:
      token_env: ABIBLIADIGITAL_TOKEN   # variável no .env com o JWT (recomendado)
      # token: "eyJ..."                 # ou coloque o token diretamente aqui
      version: nvi                      # nvi | acf | ra | kjv | bbe | apee | rvr
      mode: random                      # random | book | passage
      book: sl                          # abrev do livro — usado se mode=book (ex: gn, sl, jo)
      passage: jo:3:16                  # livro:cap:vers — usado se mode=passage
      max_items: 1                      # quantas passagens por episódio

Obtenha seu token gratuito em: https://www.abibliadigital.com.br/pt
"""

import os
import json
import hashlib
import requests
from datetime import date

BIBLE_API = "https://www.abibliadigital.com.br/api"
CACHE_PATH = "biblia_cache.json"

_BOOKS_PT = {
    # Antigo Testamento
    "gn": "Gênesis", "ex": "Êxodo", "lv": "Levítico", "nm": "Números",
    "dt": "Deuteronômio", "js": "Josué", "jz": "Juízes", "rt": "Rute",
    "1sm": "1 Samuel", "2sm": "2 Samuel", "1rs": "1 Reis", "2rs": "2 Reis",
    "1cr": "1 Crônicas", "2cr": "2 Crônicas", "ed": "Esdras", "ne": "Neemias",
    "et": "Ester", "jó": "Jó", "job": "Jó", "sl": "Salmos", "pv": "Provérbios",
    "ec": "Eclesiastes", "ct": "Cânticos", "is": "Isaías", "jr": "Jeremias",
    "lm": "Lamentações", "ez": "Ezequiel", "dn": "Daniel", "os": "Oseias",
    "jl": "Joel", "am": "Amós", "ob": "Obadias", "jn": "Jonas",
    "mq": "Miquéias", "na": "Naum", "hc": "Habacuque", "sf": "Sofonias",
    "ag": "Ageu", "zc": "Zacarias", "ml": "Malaquias",
    # Novo Testamento
    "mt": "Mateus", "mc": "Marcos", "lc": "Lucas", "jo": "João",
    "at": "Atos", "rm": "Romanos", "1co": "1 Coríntios", "2co": "2 Coríntios",
    "gl": "Gálatas", "ef": "Efésios", "fp": "Filipenses", "cl": "Colossenses",
    "1ts": "1 Tessalonicenses", "2ts": "2 Tessalonicenses",
    "1tm": "1 Timóteo", "2tm": "2 Timóteo", "tt": "Tito", "fm": "Filêmon",
    "hb": "Hebreus", "tg": "Tiago", "1pe": "1 Pedro", "2pe": "2 Pedro",
    "1jo": "1 João", "2jo": "2 João", "3jo": "3 João", "jd": "Judas",
    "ap": "Apocalipse",
}


def _book_name(abbrev: str) -> str:
    return _BOOKS_PT.get(abbrev.lower(), abbrev.upper())


def _get_token(settings: dict) -> str | None:
    env_var = settings.get('token_env', 'ABIBLIADIGITAL_TOKEN')
    return os.getenv(env_var) or settings.get('token') or None


def _headers(token: str | None) -> dict:
    h = {'Content-Type': 'application/json'}
    if token:
        h['Authorization'] = f'Bearer {token}'
    return h


def _parse_verse(data: dict, fallback_abbrev: str, source_config: dict) -> dict | None:
    """Converte a resposta da API em item RadioIA."""
    verse_text = (data.get('text') or '').strip().strip('"').strip('"').strip('"')
    if not verse_text:
        return None

    # A API retorna o livro de formas diferentes dependendo do endpoint
    book_info = data.get('book') or {}
    if isinstance(book_info, dict):
        abbrev_info = book_info.get('abbrev') or {}
        if isinstance(abbrev_info, dict):
            abbrev = abbrev_info.get('pt') or abbrev_info.get('en') or fallback_abbrev
        else:
            abbrev = str(abbrev_info) or fallback_abbrev
        book_display = book_info.get('name') or _book_name(abbrev)
    else:
        abbrev = fallback_abbrev
        book_display = _book_name(abbrev)

    chapter_raw = data.get('chapter') or data.get('chapter_number') or ''
    chapter_num = chapter_raw.get('number') if isinstance(chapter_raw, dict) else chapter_raw
    verse_num   = data.get('number') or data.get('verse') or ''

    if chapter_num and verse_num:
        ref_display = f"{book_display} {chapter_num}:{verse_num}"
        ref_spoken  = f"{book_display}, capítulo {chapter_num}, versículo {verse_num}"
    elif verse_num:
        ref_display = f"{book_display} {verse_num}"
        ref_spoken  = f"{book_display}, versículo {verse_num}"
    else:
        ref_display = ref_spoken = book_display

    version = (source_config.get('settings') or {}).get('version', 'NVI').upper()
    uid     = hashlib.md5(f"{abbrev}{chapter_num}{verse_num}{verse_text[:40]}".encode()).hexdigest()[:8]
    today   = date.today().isoformat()

    print(f"  [{version}] {ref_display} — {verse_text[:70]}{'...' if len(verse_text) > 70 else ''}")

    return {
        'id':           f"biblia-{uid}-{today}",
        'title':        ref_spoken,   # forma falada evita TTS ler "3:16" como horário
        'url':          '',
        'text':         (
            f"Passagem bíblica — {ref_spoken} ({version}):\n\n"
            f'"{verse_text}"\n\n'
            f"Livro: {book_display}"
        ),
        'source_name':  source_config.get('name', 'Palavra do Dia'),
        'source_type':  source_config.get('type', 'biblia'),
        'published_at': today,
        'views':        0,
        'comments':     [],
        'channel':      book_display,
    }


def _cache_key(version: str, mode: str, settings: dict) -> str:
    today = date.today().isoformat()
    book = str(settings.get("book", "")) if mode == "book" else ""
    return f"{today}-{version}-{mode}-{book}"


def _load_cached_items(key: str) -> list[dict] | None:
    """Lê itens cacheados para a chave do dia (evita versículo diferente a
    cada chamada do comando — 'Palavra do Dia' deve ser fixa por dia)."""
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return cache.get(key)


def _save_cached_items(key: str, items: list[dict]):
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}
    # Mantém só a entrada de hoje: chaves de dias anteriores não servem mais.
    today = date.today().isoformat()
    cache = {k: v for k, v in cache.items() if k.startswith(today)}
    cache[key] = items
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch(source_config: dict, credentials=None) -> list[dict]:
    settings  = source_config.get('settings') or {}
    token     = _get_token(settings)
    version   = settings.get('version', 'nvi').lower()
    mode      = settings.get('mode', 'random')
    max_items = max(1, int(settings.get('max_items', 1)))
    headers   = _headers(token)
    items     = []

    if not token:
        print("  [biblia] aviso: sem token — usando limite de 20 req/hora.")

    # Modos 'random'/'book' não são determinísticos na API — sem cache, cada
    # chamada do dia (manual ou automática) sorteia um versículo diferente,
    # gerando "Palavra do Dia" duplicada e inconsistente no mesmo dia.
    cache_key = None
    if mode in ('random', 'book'):
        cache_key = _cache_key(version, mode, settings)
        cached = _load_cached_items(cache_key)
        if cached is not None:
            return cached[:max_items]

    try:
        if mode == 'passage':
            passage = str(settings.get('passage', 'jo:3:16'))
            parts   = passage.split(':')
            if len(parts) != 3:
                print(f"  [biblia] 'passage' inválido: {passage!r} — use formato livro:cap:vers")
                return []
            book, chap, verse = parts
            url  = f"{BIBLE_API}/verses/{version}/{book}/{chap}/{verse}"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            item = _parse_verse(resp.json(), book, source_config)
            if item:
                items.append(item)

        elif mode == 'book':
            book = str(settings.get('book', 'sl')).lower()
            url  = f"{BIBLE_API}/verses/{version}/{book}/random"
            seen = set()
            for _ in range(max_items * 3):  # tenta até 3× para evitar duplicatas
                if len(items) >= max_items:
                    break
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                uid  = f"{data.get('chapter')}-{data.get('number')}"
                if uid in seen:
                    continue
                seen.add(uid)
                item = _parse_verse(data, book, source_config)
                if item:
                    items.append(item)

        else:  # random
            url  = f"{BIBLE_API}/verses/{version}/random"
            seen = set()
            for _ in range(max_items * 3):
                if len(items) >= max_items:
                    break
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                uid  = f"{data.get('chapter')}-{data.get('number')}"
                if uid in seen:
                    continue
                seen.add(uid)
                item = _parse_verse(data, 'desconhecido', source_config)
                if item:
                    items.append(item)

    except requests.exceptions.HTTPError as e:
        print(f"  [biblia] erro HTTP {e.response.status_code}: {e.response.text[:120]}")
    except requests.exceptions.RequestException as e:
        print(f"  [biblia] erro de conexão: {e}")
    except Exception as e:
        print(f"  [biblia] erro inesperado: {e}")

    if cache_key and items:
        _save_cached_items(cache_key, items)

    return items
