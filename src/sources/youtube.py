import random
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

MAX_TRANSCRIPT_CHARS = 600
_transcript_api = YouTubeTranscriptApi()


def _build_client(api_key: str, credentials=None):
    if credentials:
        return build("youtube", "v3", credentials=credentials)
    return build("youtube", "v3", developerKey=api_key)


def _get_uploads_playlist_id(youtube, channel_id: str) -> str | None:
    response = youtube.channels().list(id=channel_id, part="contentDetails").execute()
    items = response.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _get_recent_videos(
    youtube, playlist_id: str, max_results: int, days_lookback: int
) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback)
    response = (
        youtube.playlistItems()
        .list(playlistId=playlist_id, part="snippet", maxResults=max_results)
        .execute()
    )

    videos = []
    for item in response.get("items", []):
        snippet = item["snippet"]
        if snippet.get("title") in ("Private video", "Deleted video"):
            continue
        published_at = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
        if published_at < cutoff:
            continue
        video_id = snippet["resourceId"]["videoId"]
        videos.append(
            {
                "id": video_id,
                "title": snippet["title"],
                "channel": snippet["channelTitle"],
                "published_at": snippet["publishedAt"],
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "source_type": "video",
                "source_name": snippet["channelTitle"],
            }
        )
    return videos


def _enrich_with_stats(youtube, videos: list[dict]) -> list[dict]:
    if not videos:
        return videos
    video_ids = ",".join(v["id"] for v in videos)
    response = youtube.videos().list(id=video_ids, part="statistics,snippet").execute()

    stats_map = {}
    for item in response.get("items", []):
        stats = item.get("statistics", {})
        stats_map[item["id"]] = {
            "views": int(stats.get("viewCount", 0)),
            "description": item["snippet"].get("description", "")[:400],
        }

    for video in videos:
        extra = stats_map.get(video["id"], {})
        video["views"] = extra.get("views", 0)
        video["description"] = extra.get("description", "")
    return videos


def _get_top_comments(api_key: str, video_id: str, max_comments: int = 5) -> list[dict]:
    # Comments are public data — always use API key, never OAuth
    # (OAuth with youtube.readonly scope blocks commentThreads)
    youtube_key = _build_client(api_key)
    try:
        response = (
            youtube_key.commentThreads()
            .list(
                videoId=video_id,
                part="snippet",
                order="relevance",
                maxResults=max_comments,
                textFormat="plainText",
            )
            .execute()
        )
    except Exception:
        return []

    comments = []
    for item in response.get("items", []):
        c = item["snippet"]["topLevelComment"]["snippet"]
        text = c.get("textDisplay", "").strip()
        likes = c.get("likeCount", 0)
        author = c.get("authorDisplayName", "")
        if text and len(text) <= 220 and not text.startswith("http"):
            comments.append({"author": author, "text": text, "likes": likes})

    comments.sort(key=lambda x: x["likes"], reverse=True)
    return comments[:3]


def _try_get_transcript(video_id: str, lang_pref: list[str]) -> str:
    try:
        fetched = _transcript_api.fetch(video_id, languages=lang_pref)
        return " ".join(s.text for s in fetched)[:MAX_TRANSCRIPT_CHARS]
    except Exception:
        pass
    try:
        fetched = _transcript_api.fetch(video_id)
        return " ".join(s.text for s in fetched)[:MAX_TRANSCRIPT_CHARS]
    except Exception:
        return ""


def _fetch_from_channels(
    youtube, api_key, channels, max_per_channel, days_lookback, max_total, lang_pref
) -> list[dict]:
    videos = []
    for channel in random.sample(channels, len(channels)):
        if len(videos) >= max_total:
            break
        playlist_id = _get_uploads_playlist_id(youtube, channel["id"])
        if not playlist_id:
            continue
        recent = _get_recent_videos(youtube, playlist_id, max_per_channel, days_lookback)
        videos.extend(recent[: max_total - len(videos)])

    if videos:
        videos = _enrich_with_stats(youtube, videos)
        for video in videos:
            video["text"] = _try_get_transcript(video["id"], lang_pref)
            video["comments"] = _get_top_comments(api_key, video["id"])
    return videos


def get_subscription_channels(youtube, max_channels: int = 50) -> list[dict]:
    channels = []
    page_token = None
    while len(channels) < max_channels:
        response = (
            youtube.subscriptions()
            .list(mine=True, part="snippet", maxResults=50, pageToken=page_token)
            .execute()
        )
        for item in response.get("items", []):
            channels.append(
                {
                    "id": item["snippet"]["resourceId"]["channelId"],
                    "name": item["snippet"]["title"],
                }
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return channels


def fetch(source_config: dict, credentials=None) -> list[dict]:
    api_key = source_config["_api_key"]
    youtube = _build_client(api_key, credentials)

    channels = source_config.get("channels", [])
    settings = source_config.get("settings", {})
    max_per_channel = settings.get("max_videos_per_channel", 2)
    days_lookback = settings.get("days_lookback", 7)
    lang_pref = settings.get("language_preference", ["pt", "en"])
    max_total = settings.get("max_videos_total", 15)
    sub_ratio = settings.get("subscriptions_ratio", 0.6)

    target_from_subs = int(max_total * sub_ratio) if credentials else 0
    all_videos = []

    if credentials and target_from_subs > 0:
        print("  Buscando inscricoes...")
        sub_channels = get_subscription_channels(youtube)
        config_ids = {c["id"] for c in channels}
        sub_channels = [c for c in sub_channels if c["id"] not in config_ids]
        random.shuffle(sub_channels)
        sub_videos = _fetch_from_channels(
            youtube,
            api_key,
            sub_channels[: target_from_subs * 4],
            1,
            days_lookback,
            target_from_subs,
            lang_pref,
        )
        for v in sub_videos:
            print(f"  [inscricao] {v['title'][:65]}")
        all_videos.extend(sub_videos)

    remaining = max_total - len(all_videos)
    if remaining > 0:
        config_videos = _fetch_from_channels(
            youtube, api_key, channels, max_per_channel, days_lookback, remaining, lang_pref
        )
        for v in config_videos:
            print(f"  [config]   {v['title'][:65]}")
        all_videos.extend(config_videos)

    return all_videos[:max_total]


def search_youtube_by_keyword(
    query: str, youtube_service, max_results: int = 3, published_after_hours: int = 48
) -> list:
    """
    Busca vídeos recentes no YouTube por keyword.
    Retorna lista de itens no mesmo formato das outras sources.
    """
    import logging
    from datetime import datetime, timedelta, timezone

    logger = logging.getLogger(__name__)

    published_after = datetime.now(timezone.utc) - timedelta(hours=published_after_hours)
    published_after_str = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        response = (
            youtube_service.search()
            .list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                publishedAfter=published_after_str,
                relevanceLanguage="pt",
                regionCode="BR",
                order="relevance",
            )
            .execute()
        )

        items = []
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            items.append(
                {
                    "id": video_id,
                    "title": snippet.get("title", ""),
                    "url": f"https://youtube.com/watch?v={video_id}",
                    "text": snippet.get("description", "")[:300],
                    "source_name": snippet.get("channelTitle", "YouTube"),
                    "source_id": "youtube",
                    "source_type": "youtube",
                    "published_at": snippet.get("publishedAt", ""),
                    "image": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                    "channel": snippet.get("channelTitle", ""),
                    "views": 0,
                }
            )
        return items

    except Exception as e:
        logger.warning(f'[youtube_keyword] erro para "{query}": {e}')
        return []
