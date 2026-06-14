"""
Clips atômicos de hora e minuto para avisos de grade.

Estrutura em disco:
  output/_time_clips/atomic/h00.mp3 … h23.mp3   (24 clips de hora)
  output/_time_clips/atomic/m01.mp3 … m59.mp3   (59 clips de minuto)
  output/_time_clips/09-15.mp3                  (combinados, gerados lazy)
"""

import asyncio
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydub import AudioSegment

TIME_CLIPS_DIR = os.path.join("output", "_time_clips")
ATOMIC_DIR = os.path.join(TIME_CLIPS_DIR, "atomic")

# ── Texto em português ────────────────────────────────────────────────────────

_ONES_M = [
    "zero",
    "um",
    "dois",
    "três",
    "quatro",
    "cinco",
    "seis",
    "sete",
    "oito",
    "nove",
    "dez",
    "onze",
    "doze",
    "treze",
    "quatorze",
    "quinze",
    "dezesseis",
    "dezessete",
    "dezoito",
    "dezenove",
]
_ONES_F = [
    "zero",
    "uma",
    "duas",
    "três",
    "quatro",
    "cinco",
    "seis",
    "sete",
    "oito",
    "nove",
    "dez",
    "onze",
    "doze",
    "treze",
    "quatorze",
    "quinze",
    "dezesseis",
    "dezessete",
    "dezoito",
    "dezenove",
]
_TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta"]


def _num(n: int, fem: bool = False) -> str:
    ones = _ONES_F if fem else _ONES_M
    if n < 20:
        return ones[n]
    t, u = _TENS[n // 10], n % 10
    return t if u == 0 else f"{t} e {ones[u]}"


def _hour_text(h: int) -> str:
    if h == 1:
        return "É uma hora"
    return f"São {_num(h, fem=True)} horas"


def _minute_text(m: int) -> str:
    word = "minuto" if m == 1 else "minutos"
    return f"e {_num(m)} {word}"


# ── Paths ─────────────────────────────────────────────────────────────────────


def _atomic_path(kind: str, n: int) -> str:
    return os.path.join(ATOMIC_DIR, f"{kind}{n:02d}.mp3")


def _assembled_path(h: int, m: int) -> str:
    return os.path.join(TIME_CLIPS_DIR, f"{h:02d}-{m:02d}.mp3")


# ── Geração ───────────────────────────────────────────────────────────────────


async def _tts_save(text: str, voice: str, rate: str, path: str):
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate).save(path)


def generate_atomic_clips(
    voice: str = "pt-BR-FranciscaNeural", rate: str = "+15%", force: bool = False
) -> int:
    """Gera os 83 clips atômicos (24 horas + 59 minutos). Retorna quantos foram criados."""
    os.makedirs(ATOMIC_DIR, exist_ok=True)

    tasks: list[tuple[str, str]] = []
    for h in range(24):
        p = _atomic_path("h", h)
        if force or not os.path.exists(p):
            tasks.append((p, _hour_text(h)))
    for m in range(1, 60):
        p = _atomic_path("m", m)
        if force or not os.path.exists(p):
            tasks.append((p, _minute_text(m)))

    if not tasks:
        return 0

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def _run():
        sem = asyncio.Semaphore(5)

        async def _one(path: str, text: str):
            async with sem:
                await _tts_save(text, voice, rate, path)

        await asyncio.gather(*[_one(p, t) for p, t in tasks])

    asyncio.run(_run())

    # Apaga combinados existentes para que sejam remontados com o novo trim
    if force and os.path.isdir(TIME_CLIPS_DIR):
        for f in os.listdir(TIME_CLIPS_DIR):
            if f.endswith(".mp3") and f[0].isdigit():
                os.remove(os.path.join(TIME_CLIPS_DIR, f))

    return len(tasks)


# ── Montagem lazy ─────────────────────────────────────────────────────────────


def _trim(
    audio: "AudioSegment", trim_start: bool = True, trim_end: bool = True, thresh_db: int = -45
) -> "AudioSegment":
    """Remove silêncio inicial e/ou final de um clip."""
    from pydub.silence import detect_leading_silence

    start = (
        detect_leading_silence(audio, silence_threshold=thresh_db, chunk_size=5)
        if trim_start
        else 0
    )
    end = (
        detect_leading_silence(audio.reverse(), silence_threshold=thresh_db, chunk_size=5)
        if trim_end
        else 0
    )
    trimmed = audio[start : len(audio) - end if end else len(audio)]
    return trimmed if len(trimmed) > 100 else audio  # fallback se trim excessivo


def get_time_clip(h: int, m: int) -> bytes | None:
    """
    Retorna bytes MP3 do clip de tempo (ex: "São nove horas e quinze minutos").
    Monta e salva em disco na primeira chamada para cada HH:MM.
    Retorna None se os atômicos ainda não foram gerados.
    """
    from pydub import AudioSegment

    assembled = _assembled_path(h, m)
    if os.path.exists(assembled):
        with open(assembled, "rb") as f:
            return f.read()

    h_path = _atomic_path("h", h)
    if not os.path.exists(h_path):
        return None

    # Apara silêncio final da hora para eliminar pausa entre os clips
    audio = _trim(AudioSegment.from_mp3(h_path), trim_start=False, trim_end=True)

    if m > 0:
        m_path = _atomic_path("m", m)
        if not os.path.exists(m_path):
            return None
        # Apara silêncio inicial do minuto e une com pausa mínima
        m_audio = _trim(AudioSegment.from_mp3(m_path), trim_start=True, trim_end=False)
        audio = audio + AudioSegment.silent(60) + m_audio

    audio = audio + AudioSegment.silent(300)

    os.makedirs(TIME_CLIPS_DIR, exist_ok=True)
    audio.export(assembled, format="mp3", bitrate="64k")

    with open(assembled, "rb") as f:
        return f.read()
