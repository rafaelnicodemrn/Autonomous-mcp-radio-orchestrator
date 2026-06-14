"""
Plugin GDELT — notícias globais com foco em Brasil via API gratuita pública.
Sem autenticação. Sem limite de uso.
Uso via main.py: python main.py gdelt
"""
import logging

import requests

logger = logging.getLogger(__name__)

PLUGIN_ID = 'gdelt'
PLUGIN_NAME = 'GDELT Brasil'

# Queries focadas no perfil do usuário
QUERIES = [
    'Brasil política conservador',
    'agronegócio Paraná Brasil',
    'catolicismo Igreja Brasil',
    'tecnologia inteligência artificial Brasil',
]


def fetch(source_config: dict, credentials=None) -> list:
    """Busca artigos recentes no GDELT sobre temas do perfil."""
    items = []

    for query in QUERIES:
        try:
            encoded = requests.utils.quote(query)
            url = (
                f"https://api.gdeltproject.org/api/v2/doc/doc"
                f"?query={encoded} sourcelang:portuguese"
                f"&mode=artlist&maxrecords=5&format=json"
            )
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue

            data = resp.json()
            for art in data.get('articles', []):
                title = art.get('title', '').strip()
                url_art = art.get('url', '').strip()
                if not title or not url_art:
                    continue
                items.append({
                    'id': url_art,
                    'title': title,
                    'url': url_art,
                    'text': title,
                    'source_name': art.get('domain', 'GDELT'),
                    'source_id': PLUGIN_ID,
                    'source_type': 'rss',
                    'published_at': art.get('seendate', ''),
                    'image': None,
                })
        except Exception as e:
            logger.warning(f'[gdelt] erro para "{query}": {e}')

    logger.info(f'[gdelt] {len(items)} artigos coletados')
    return items
