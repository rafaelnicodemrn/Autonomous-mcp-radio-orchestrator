# src/content_enricher.py
# Enriquecimento de conteúdo: imagens, deduplicação, score de relevância, tradução
import os
import json
import hashlib
import difflib
import re
import logging
from datetime import datetime, date
from typing import Optional

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join('output', '_telegram_cache')
IMG_CACHE_DIR = os.path.join(CACHE_DIR, 'images')
TRANS_CACHE_FILE = os.path.join(CACHE_DIR, 'translations.json')

# Palavras-chave do perfil do Rafael
USER_KEYWORDS = [
    'grêmio', 'gremio', 'tricolor', 'futebol', 'brasileirão', 'brasileirao',
    'católico', 'catolicismo', 'católica', 'vaticano', 'papa', 'padre', 'fé',
    'tecnologia', 'inteligência artificial', 'ia', 'tech', 'software', 'programação',
    'conservador', 'conservadorismo', 'liberdade', 'direita', 'mises', 'burke',
    'agronegócio', 'agronegocio', 'agro', 'rural', 'soja', 'milho',
    'paraná', 'parana', 'medianeira', 'cascavel', 'oeste',
    'copa', 'seleção', 'selecao', 'brasil', 'libertadores',
    'filosofia', 'teologia', 'igreja', 'cristo', 'deus', 'bíblia', 'biblia',
    'luxemburgo', 'europa', 'portugal', 'france', 'italia',
]

TRUSTED_SOURCES = [
    'vatican news', 'padre paulo', 'canção nova', 'cancao nova', 'aci digital',
    'tfp', 'burke', 'mises', 'gazeta do povo', 'jovem pan', 'gremio', 'grêmio',
    'espn', 'ge ', 'gauchazh', 'wall street journal', 'wsj',
]


def _ensure_cache():
    os.makedirs(IMG_CACHE_DIR, exist_ok=True)


def _img_cache_path(url: str) -> str:
    key = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(IMG_CACHE_DIR, key + '.url')


# ── 1. Extração de imagem ─────────────────────────────────────────────────────

def extract_image(url: str, item: dict) -> Optional[str]:
    """Retorna URL de imagem para o item. Usa cache para não rebuscar."""
    _ensure_cache()

    if not url:
        return _extract_from_item(item)

    cache_path = _img_cache_path(url)
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            cached = f.read().strip()
        return cached if cached else None

    # YouTube: extrai thumbnail direto
    yt_match = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    if yt_match:
        img_url = f"https://img.youtube.com/vi/{yt_match.group(1)}/maxresdefault.jpg"
        _save_img_cache(cache_path, img_url)
        return img_url

    # Tenta og:image
    try:
        resp = requests.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; RadioIA/1.0)'
        })
        soup = BeautifulSoup(resp.text, 'html.parser')
        og = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
        if og and og.get('content'):
            img_url = og['content']
            _save_img_cache(cache_path, img_url)
            return img_url
    except Exception:
        pass

    # Fallback: item RSS
    img_url = _extract_from_item(item)
    _save_img_cache(cache_path, img_url or '')
    return img_url


def _extract_from_item(item: dict) -> Optional[str]:
    """Tenta extrair imagem dos metadados do item."""
    # Campo image direto
    if item.get('image'):
        return item['image']
    # YouTube thumbnail via channel/video id
    if item.get('source_type') == 'youtube' and item.get('url'):
        yt_match = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', item['url'])
        if yt_match:
            return f"https://img.youtube.com/vi/{yt_match.group(1)}/maxresdefault.jpg"
    return None


def _save_img_cache(path: str, value: str):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(value)
    except Exception:
        pass


# ── 2. Score de relevância ────────────────────────────────────────────────────

def score_item(item: dict) -> int:
    """Pontua item de 0 a 10 com base no perfil do usuário."""
    score = 0
    text = ' '.join([
        str(item.get('title', '')),
        str(item.get('text', ''))[:500],
        str(item.get('source_name', '')),
        str(item.get('channel', '')),
    ]).lower()

    # Palavras-chave do perfil
    matches = sum(1 for kw in USER_KEYWORDS if kw in text)
    score += min(matches * 2, 5)

    # Fonte confiável
    source = str(item.get('source_name', '')).lower()
    if any(ts in source for ts in TRUSTED_SOURCES):
        score += 2

    # Recência
    pub = item.get('published_at', '')
    if pub:
        try:
            pub_date = datetime.fromisoformat(str(pub)[:10]).date()
            today = date.today()
            delta = (today - pub_date).days
            if delta == 0:
                score += 2
            elif delta == 1:
                score += 1
        except Exception:
            pass

    # Tem imagem
    if item.get('image') or item.get('url', ''):
        score += 1

    # Tem link
    if item.get('url'):
        score += 1

    return min(score, 10)


# ── 3. Deduplicação ───────────────────────────────────────────────────────────

def _normalize_title(title: str) -> str:
    """Normaliza título: lowercase, remove stopwords e pontuação."""
    title = title.lower()
    title = re.sub(r'[^\w\s]', '', title)
    stopwords = {
        'o', 'a', 'os', 'as', 'de', 'do', 'da', 'dos', 'das', 'em', 'no', 'na',
        'nos', 'nas', 'e', 'ou', 'que', 'um', 'uma', 'para', 'por', 'com',
        'se', 'é', 'são', 'foi', 'ser', 'ter', 'tem', 'sobre', 'após',
    }
    words = [w for w in title.split() if w not in stopwords and len(w) > 2]
    return ' '.join(words[:8])


def deduplicate(items: list) -> list:
    """
    Remove itens duplicados por URL idêntica ou título similar (threshold 0.55).
    Mantém item com maior _score.
    """
    if not items:
        return items

    # Garante que todos têm _score
    for item in items:
        if '_score' not in item:
            item['_score'] = score_item(item)

    # Dedup por URL idêntica primeiro
    seen_urls = {}
    url_deduped = []
    for item in items:
        url = item.get('url', '')
        if url and url in seen_urls:
            existing = seen_urls[url]
            if item['_score'] > existing['_score']:
                url_deduped.remove(existing)
                url_deduped.append(item)
                seen_urls[url] = item
        else:
            url_deduped.append(item)
            if url:
                seen_urls[url] = item

    # Dedup por similaridade de título
    unique = []
    for item in url_deduped:
        norm_title = _normalize_title(str(item.get('title', '')))
        is_dup = False
        for kept in unique:
            kept_norm = _normalize_title(str(kept.get('title', '')))
            ratio = difflib.SequenceMatcher(None, norm_title, kept_norm).ratio()
            if ratio >= 0.55:
                if item['_score'] > kept['_score']:
                    unique.remove(kept)
                    unique.append(item)
                is_dup = True
                logger.debug(f"[dedup] removido (ratio={ratio:.2f}): {item.get('title','')[:60]}")
                break
        if not is_dup:
            unique.append(item)

    return unique


# ── 3b. Diversidade de tópicos ────────────────────────────────────────────────

TOPIC_KEYWORDS = {
    'copa': ['copa', 'mundial', 'seleção', 'selecao', 'fifa', 'libertadores'],
    'gremio': ['grêmio', 'gremio', 'tricolor', 'arena'],
    'ia': ['inteligência artificial', 'ia', 'gemini', 'gpt', 'openai', 'machine learning'],
    'papa': ['papa', 'vaticano', 'igreja', 'pontífice', 'pontifice'],
    'politica_br': ['política', 'politica', 'governo', 'congresso', 'eleição', 'eleicao', 'presidente'],
    'economia': ['economia', 'inflação', 'inflacao', 'juros', 'dólar', 'dolar', 'pib'],
}


def _detect_topic(item: dict) -> Optional[str]:
    """Detecta a qual tópico (se algum) um item pertence."""
    text = ' '.join([
        str(item.get('title', '')),
        str(item.get('source_name', '')),
    ]).lower()

    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return topic

    return None


def diversity_guard(items: list, max_per_topic: int = 2) -> list:
    """
    Limita quantos itens de cada tópico (ex: copa, grêmio, papa) aparecem
    na lista final, evitando que um único assunto domine o briefing.
    Itens sem tópico detectado não são limitados. Mantém a ordem original
    (que já vem ordenada por score).
    """
    if not items:
        return items

    topic_counts = {}
    result = []

    for item in items:
        topic = _detect_topic(item)
        if topic is None:
            result.append(item)
            continue

        count = topic_counts.get(topic, 0)
        if count < max_per_topic:
            result.append(item)
            topic_counts[topic] = count + 1
        else:
            logger.debug(f"[diversity] removido (tópico={topic} cheio): {item.get('title','')[:60]}")

    return result


# ── 4. Tradução EN→PT ─────────────────────────────────────────────────────────

def _load_trans_cache() -> dict:
    if os.path.exists(TRANS_CACHE_FILE):
        try:
            with open(TRANS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_trans_cache(cache: dict):
    _ensure_cache()
    try:
        with open(TRANS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _is_english(text: str) -> bool:
    """Heurística simples: detecta inglês pela frequência de palavras comuns."""
    en_words = {'the', 'and', 'for', 'that', 'this', 'with', 'are', 'was',
                'has', 'have', 'will', 'from', 'they', 'been', 'says', 'said',
                'new', 'year', 'after', 'also', 'into', 'its', 'more'}
    words = set(re.findall(r'\b[a-z]{2,}\b', text.lower()))
    overlap = words & en_words
    return len(overlap) >= 4


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=False)
def _gemini_call_with_retry(prompt: str, model: str, max_tokens: int) -> str:
    """Wrapper com retry automático para chamadas ao Gemini."""
    from litellm import completion
    response = completion(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=max_tokens,
        timeout=15,
    )
    return response.choices[0].message.content.strip()


def translate_if_needed(title: str, text: str) -> tuple:
    """Traduz título e texto se estiverem em inglês. Retorna (title, text)."""
    combined = f"{title} {text[:200]}"
    if not _is_english(combined):
        return title, text

    cache = _load_trans_cache()
    key = hashlib.md5(title.encode()).hexdigest()

    if key in cache:
        cached = cache[key]
        return cached.get('title', title), cached.get('text', text)

    try:
        from dotenv import load_dotenv
        load_dotenv()

        prompt = (
            "Traduza para português brasileiro de forma natural, mantendo nomes próprios. "
            "Responda APENAS com JSON: {\"title\": \"...\", \"text\": \"...\"}\n\n"
            f"Título: {title}\n\nTexto: {text[:400]}"
        )

        raw = _gemini_call_with_retry(
            prompt,
            os.getenv('TELEGRAM_LLM_MODEL', 'gemini/gemini-2.5-flash-lite'),
            600,
        )
        raw = re.sub(r'^```json|```$', '', raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        t_title = data.get('title', title)
        t_text = data.get('text', text)

        cache[key] = {'title': t_title, 'text': t_text}
        _save_trans_cache(cache)
        return t_title, t_text

    except Exception as e:
        logger.warning(f"[translate] falhou: {e}")
        return title, text


# ── 5. Enrich completo ────────────────────────────────────────────────────────

def enrich_item(item: dict) -> dict:
    """Aplica todas as transformações em um item e retorna versão enriquecida."""
    url = item.get('url', '')
    title = item.get('title', '')
    text = item.get('text', '')

    # Tradução
    title, text = translate_if_needed(title, text)

    # Imagem
    image_url = extract_image(url, item)

    # Score
    enriched_item = dict(item)
    enriched_item['title'] = title
    enriched_item['text'] = text
    enriched_item['_image_url'] = image_url
    enriched_item['_score'] = score_item(enriched_item)

    return enriched_item
