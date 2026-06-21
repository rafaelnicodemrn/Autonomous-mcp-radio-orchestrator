import random
from datetime import datetime, timedelta, timezone

import feedparser
import trafilatura

MAX_ARTICLE_CHARS = 1200


def _parse_date(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def _extract_text(url: str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded, include_comments=False, include_tables=False, no_fallback=False
            )
            return (text or "")[:MAX_ARTICLE_CHARS]
    except Exception:
        pass
    return ""


def fetch(source_config: dict, credentials=None) -> list[dict]:
    feeds = source_config.get("feeds", [])
    settings = source_config.get("settings", {})
    max_per_feed = settings.get("max_items_per_feed", 3)
    max_total = settings.get("max_items_total", 10)
    days_lookback = settings.get("days_lookback", 1)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback)

    feeds = random.sample(feeds, len(feeds))  # ordem aleatória a cada execução
    all_items = []
    for feed_config in feeds:
        if len(all_items) >= max_total:
            break

        feed = feedparser.parse(feed_config["url"])
        feed_name = feed_config.get("name", feed.feed.get("title", "Feed"))
        count = 0

        for entry in feed.entries:
            if count >= max_per_feed or len(all_items) >= max_total:
                break

            published = _parse_date(entry)
            if published and published < cutoff:
                continue

            url = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not url or not title:
                continue

            summary = entry.get("summary", "")
            text = _extract_text(url) or summary[:MAX_ARTICLE_CHARS]

            all_items.append(
                {
                    "id": url,
                    "title": title,
                    "url": url,
                    "text": text,
                    "source_name": feed_name,
                    "source_type": "news",
                    # Sem data confiável: deixa em branco (recência neutra) em vez
                    # de fingir que é "agora" — item sem published_parsed pode ser
                    # antigo e, fabricando a data, escaparia do filtro de cutoff
                    # e ainda ganharia bônus de recência máximo indevidamente.
                    "published_at": published.isoformat() if published else "",
                    "views": 0,
                    "comments": [],
                    "channel": feed_name,
                }
            )
            count += 1
            print(f"  [{feed_name}] {title[:70]}")

    return all_items
