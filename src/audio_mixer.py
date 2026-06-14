import json
import os

from pydub import AudioSegment

PAUSE_SAME_SPEAKER_MS = 150
PAUSE_DIFF_SPEAKER_MS = 500

TRANSITION_PHRASES = (
    "proximo",
    "mudando",
    "tem mais",
    "olha so",
    "agora vamos",
    "continuando",
    "falando em",
    "e por falar",
    "e por ultimo",
)


def _generate_transition_tone() -> AudioSegment:
    try:
        from pydub.generators import Sine

        tone = Sine(880).to_audio_segment(duration=80).apply_gain(-18).fade_in(10).fade_out(20)
        return AudioSegment.silent(350) + tone + AudioSegment.silent(350)
    except Exception:
        return AudioSegment.silent(700)


def _overlay_background_music(
    speech: AudioSegment, music_path: str, volume_db: float
) -> AudioSegment:
    music = AudioSegment.from_file(music_path)
    looped = music
    while len(looped) < len(speech):
        looped += music
    looped = looped[: len(speech)].fade_in(2000).fade_out(4000)
    return speech.overlay(looped + volume_db)


def _is_transition_line(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in TRANSITION_PHRASES)


def mix_episode(
    audio_files: list[str],
    lines: list[dict],
    output_path: str,
    metadata: dict,
    radio_config: dict | None = None,
    vinhetas: dict | None = None,
    station_name: str = "RadioIA",
) -> float:
    radio_config = radio_config or {}
    vinhetas = vinhetas or {}
    fallback_tone = _generate_transition_tone()

    combined = AudioSegment.empty()

    # Opening vinheta
    if "abertura" in vinhetas:
        combined += vinhetas["abertura"]

    for i, (file_path, line) in enumerate(zip(audio_files, lines)):
        if i > 0 and _is_transition_line(line["text"]):
            combined += vinhetas.get("id", fallback_tone)

        segment = AudioSegment.from_mp3(file_path)
        combined += segment

        if i < len(lines) - 1:
            next_speaker = lines[i + 1]["locutor"]
            pause_ms = (
                PAUSE_DIFF_SPEAKER_MS if next_speaker != line["locutor"] else PAUSE_SAME_SPEAKER_MS
            )
            combined += AudioSegment.silent(duration=pause_ms)

    # Closing vinheta
    if "encerramento" in vinhetas:
        combined += vinhetas["encerramento"]

    music_path = radio_config.get("background_music", "")
    if music_path and os.path.exists(music_path):
        volume_db = radio_config.get("background_volume_db", -22)
        combined = _overlay_background_music(combined, music_path, volume_db)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    combined.export(
        output_path,
        format="mp3",
        bitrate="128k",
        tags={
            "title": metadata.get("title", station_name),
            "artist": station_name,
            "comment": metadata.get("links_text", ""),
        },
    )

    return len(combined) / 1000


def save_episode_metadata(
    videos: list[dict], script: str, output_dir: str, duration_secs: float, source_name: str = ""
) -> dict:
    links = [
        {
            "title": v["title"],
            "channel": v["channel"],
            "url": v["url"],
            "views": v.get("views", 0),
            "published_at": v.get("published_at", ""),
            "top_comments": v.get("comments", []),
        }
        for v in videos
    ]
    metadata = {
        "source_name": source_name,
        "duration_seconds": round(duration_secs),
        "videos_covered": len(videos),
        "links": links,
    }

    with open(os.path.join(output_dir, "episode.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "script.txt"), "w", encoding="utf-8") as f:
        f.write(script)

    return metadata
