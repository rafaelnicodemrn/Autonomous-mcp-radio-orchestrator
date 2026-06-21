"""
Plugin GDELT — notícias globais com foco em Brasil via API gratuita pública.
Sem autenticação. Sem limite de uso.
Uso via main.py: python main.py gdelt
Para customizar os temas buscados: python main.py gdelt:catolicismo,politica,conservadorismo
"""

import logging

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

PLUGIN_ID = "gdelt"
PLUGIN_NAME = "GDELT Brasil"

GDELT_TIMEOUT = 20

# Queries padrão focadas no perfil do usuário
QUERIES = [
    "Brasil política conservador",
    "agronegócio Paraná Brasil",
    "catolicismo Igreja Brasil",
    "tecnologia inteligência artificial Brasil",
]


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=4),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)
def _fetch_query(query: str) -> dict:
    encoded = requests.utils.quote(query)
    url = (
        f"https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={encoded} sourcelang:portuguese"
        f"&mode=artlist&maxrecords=5&format=json"
    )
    resp = requests.get(url, timeout=GDELT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch(source_config: dict, credentials=None) -> list:
    """Busca artigos recentes no GDELT sobre temas do perfil.

    Aceita override dos temas via parâmetro CLI (gdelt:tema1,tema2,...).
    """
    items = []

    param = (source_config or {}).get("_param")
    queries = [t.strip() for t in param.split(",") if t.strip()] if param else QUERIES

    for query in queries:
        try:
            data = _fetch_query(query)
            for art in data.get("articles", []):
                title = art.get("title", "").strip()
                url_art = art.get("url", "").strip()
                if not title or not url_art:
                    continue
                items.append(
                    {
                        "id": url_art,
                        "title": title,
                        "url": url_art,
                        "text": title,
                        "source_name": art.get("domain", "GDELT"),
                        "source_id": PLUGIN_ID,
                        "source_type": "rss",
                        "published_at": art.get("seendate", ""),
                        "image": None,
                    }
                )
        except Exception as e:
            logger.warning(f'[gdelt] erro para "{query}": {e}')

    logger.info(f"[gdelt] {len(items)} artigos coletados")
    return items
