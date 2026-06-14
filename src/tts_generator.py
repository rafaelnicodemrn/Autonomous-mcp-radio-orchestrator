import asyncio
import html
import os
import re
import sys

MAX_LINE_CHARS = 450


def parse_script(script: str) -> list[dict]:
    lines = []
    pattern = re.compile(r"\*{0,2}\[(LOCUTOR_[A-C])\]\*{0,2}:[\*\s]*(.+)")
    for line in script.splitlines():
        match = pattern.match(line.strip())
        if match:
            locutor, text = match.groups()
            text = _sanitize(text.strip())
            if text:
                lines.append({"locutor": locutor, "text": text})
    return lines


def _sanitize(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\*+", "", text)
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = re.sub(r"[^\w\s,\.!?;:\-\(\)\"\'À-ɏ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_LINE_CHARS]


async def _generate_line(provider, text: str, voice: str, output_path: str) -> None:
    await provider.synthesize(text, voice, output_path)


async def _generate_all(lines: list[dict], voices: dict, temp_dir: str, provider) -> list[str]:
    paths = [os.path.join(temp_dir, f"line_{i:04d}.mp3") for i in range(len(lines))]

    batch_size = 3
    for batch_start in range(0, len(lines), batch_size):
        batch_end = min(batch_start + batch_size, len(lines))
        batch = lines[batch_start:batch_end]

        for attempt in range(3):
            tasks = [
                _generate_line(
                    provider, line["text"], voices[line["locutor"]], paths[batch_start + j]
                )
                for j, line in enumerate(batch)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = [r for r in results if isinstance(r, BaseException)]

            if not errors:
                break
            if attempt < 2:
                print(
                    f"  [tts] batch {batch_start//batch_size+1} falhou, "
                    f"tentando novamente ({attempt+2}/3)..."
                )
                await asyncio.sleep(3.0 * (attempt + 1))
            else:
                raise RuntimeError(f"TTS: batch falhou após 3 tentativas — {errors[0]}")

        if batch_end < len(lines):
            await asyncio.sleep(0.5)

    return paths


def generate_audio_files(
    lines: list[dict], voices: dict, temp_dir: str, tts_config: dict = None
) -> list[str]:
    from src.tts_providers import get_provider

    provider = get_provider(tts_config or {})

    os.makedirs(temp_dir, exist_ok=True)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    return asyncio.run(_generate_all(lines, voices, temp_dir, provider))
