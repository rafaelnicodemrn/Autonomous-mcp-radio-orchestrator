import asyncio
import os
import sys

from pydub import AudioSegment


def _make_sting() -> AudioSegment:
    try:
        from pydub.generators import Sine

        notes = [523, 659, 784, 1047]  # C5 E5 G5 C6
        sting = AudioSegment.empty()
        for freq in notes:
            tone = Sine(freq).to_audio_segment(duration=70).apply_gain(-14).fade_in(5).fade_out(15)
            sting += tone
        return sting
    except Exception:
        return AudioSegment.silent(300)


async def _build_all(
    texts: dict, voice: str, rate: str, temp_dir: str, provider
) -> dict[str, AudioSegment]:
    results = {}
    for key, text in texts.items():
        path = os.path.join(temp_dir, f"vinheta_{key}.mp3")
        await provider.synthesize(text, voice, path, rate=rate)
        speech = AudioSegment.from_mp3(path)

        if key == "id":
            audio = _make_sting() + AudioSegment.silent(100) + speech + AudioSegment.silent(400)
        elif key == "abertura":
            audio = _make_sting() + AudioSegment.silent(150) + speech + AudioSegment.silent(500)
        else:
            audio = AudioSegment.silent(300) + speech + AudioSegment.silent(150) + _make_sting()

        results[key] = audio
    return results


def generate_vinhetas(
    config: dict, temp_dir: str, tts_config: dict = None
) -> dict[str, AudioSegment]:
    from src.tts_providers import get_provider

    provider = get_provider(tts_config or {})

    voice = config.get("voice", "pt-BR-ThalitaNeural")
    station = config.get("station_name", "RadioIA")
    rate = config.get("rate", "+20%")

    texts = {
        "abertura": config.get("abertura", f"{station} — sua rádio personalizada!"),
        "id": config.get("id", station + "!"),
        "encerramento": config.get("encerramento", f"{station} — até o próximo episódio!"),
    }

    os.makedirs(temp_dir, exist_ok=True)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    return asyncio.run(_build_all(texts, voice, rate, temp_dir, provider))
