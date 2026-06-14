import sys
import os
import copy

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'src'))


@pytest.fixture
def sample_config():
    """Config mínima para testes (sem credenciais reais)."""
    return {
        "perfil": {
            "nome": "Rafael",
            "interesses_primarios": ["tecnologia", "futebol", "fé"],
            "fontes_vip": ["G1"],
            "ignorar_sempre": ["fofoca e celebridades", "horóscopo"],
            "idioma_preferido": "pt-BR",
            "score_minimo_enviar": 5,
            "max_cards_por_comando": 8,
        },
        "telegram": {
            "quotas": {
                "briefing": {"max_total": 10, "max_por_fonte": 3},
            }
        },
    }


@pytest.fixture
def empty_adaptive_state():
    """Estado adaptativo vazio (DEFAULT_STATE)."""
    from src.adaptive_engine import DEFAULT_STATE
    return copy.deepcopy(DEFAULT_STATE)


@pytest.fixture
def sample_item():
    """Item de conteúdo representativo para testes."""
    return {
        "title": "Grêmio vence clássico por 2 a 1",
        "source_name": "gaucha_rss",
        "source_id": "gaucha_001",
        "published_at": "2025-06-10T10:00:00",
        "text": "Em jogo disputado no Beira-Rio, o Grêmio venceu por 2 a 1.",
        "_score": 7.5,
    }


@pytest.fixture
def sample_items(sample_item):
    """Lista de itens para testar filtragem e dedup."""
    items = []
    for i in range(10):
        item = dict(sample_item)
        item["title"] = f"Notícia {i}"
        item["source_id"] = f"src_{i:03d}"
        item["_score"] = float(i)
        items.append(item)
    return items
