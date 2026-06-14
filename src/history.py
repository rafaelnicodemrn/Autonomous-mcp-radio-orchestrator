import json
import os

HISTORY_PATH = "history.json"


def load_seen_ids() -> set[str]:
    if not os.path.exists(HISTORY_PATH):
        return set()
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("seen_ids", []))


def save_episode_to_history(episode_id: str, videos: list[dict]):
    seen_ids = load_seen_ids()

    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"seen_ids": [], "episodes": []}

    new_ids = [v["id"] for v in videos]
    seen_ids.update(new_ids)
    data["seen_ids"] = list(seen_ids)
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
