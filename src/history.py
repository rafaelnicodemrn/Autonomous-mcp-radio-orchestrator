import json
import os
from datetime import date, datetime, timedelta

HISTORY_PATH = "history.json"

# Itens marcados como "já vistos" expiram depois deste período: RSS não
# costuma reciclar itens antigos como novos, então manter o histórico para
# sempre apenas esgota o estoque de conteúdo "novo" das fontes (esvaziando
# o briefing) sem nenhum benefício de dedup real.
SEEN_IDS_TTL_DAYS = 21


def _load_raw() -> dict:
    if not os.path.exists(HISTORY_PATH):
        return {"seen_ids": {}, "episodes": []}
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Compatibilidade com formato antigo: seen_ids era uma lista sem data.
    # Trata como vistos "hoje" para não perder o efeito de dedup imediato.
    seen = data.get("seen_ids", {})
    if isinstance(seen, list):
        today = date.today().isoformat()
        seen = {item_id: today for item_id in seen}
    data["seen_ids"] = seen
    return data


def _prune_expired(seen: dict) -> dict:
    cutoff = date.today() - timedelta(days=SEEN_IDS_TTL_DAYS)
    pruned = {}
    for item_id, seen_at in seen.items():
        try:
            seen_date = datetime.fromisoformat(str(seen_at)[:10]).date()
        except (ValueError, TypeError):
            continue
        if seen_date >= cutoff:
            pruned[item_id] = seen_at
    return pruned


def load_seen_ids() -> set[str]:
    data = _load_raw()
    return set(_prune_expired(data["seen_ids"]).keys())


def save_episode_to_history(episode_id: str, videos: list[dict]):
    data = _load_raw()
    seen = _prune_expired(data["seen_ids"])

    today = date.today().isoformat()
    for v in videos:
        seen[v["id"]] = today
    data["seen_ids"] = seen

    data.setdefault("episodes", [])
    data["episodes"].append(
        {
            "episode_id": episode_id,
            "videos": [
                {"id": v["id"], "title": v["title"], "channel": v["channel"]} for v in videos
            ],
        }
    )

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
