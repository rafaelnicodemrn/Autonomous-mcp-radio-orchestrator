"""Provider edge-tts (padrão) — Microsoft Neural TTS via Edge browser, sem custo."""

import asyncio

import edge_tts

MAX_CHARS = 450  # limite conservador para evitar timeout no edge-tts


class EdgeTTSProvider:
    def __init__(self, config: dict):
        self._config = config or {}

    async def synthesize(
        self, text: str, voice: str, output_path: str, rate: str = "+0%", retries: int = 4
    ) -> None:
        text = text[:MAX_CHARS]
        for attempt in range(retries):
            try:
                await edge_tts.Communicate(text, voice, rate=rate).save(output_path)
                return
            except BaseException as e:
                if attempt < retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                else:
                    # Última tentativa com texto reduzido
                    try:
                        await edge_tts.Communicate(text[:200], voice, rate=rate).save(output_path)
                        return
                    except BaseException:
                        raise RuntimeError(
                            f"EdgeTTS falhou após {retries} tentativas: {e}\nTexto: {text[:80]}"
                        )
