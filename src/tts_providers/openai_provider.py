"""Provider OpenAI TTS — requer: pip install openai
Vozes disponíveis: alloy, ash, coral, echo, fable, onyx, nova, sage, shimmer
Modelos: tts-1 (rápido) | tts-1-hd (maior qualidade)

Configuração em config.yaml:
  tts:
    provider: openai
    openai:
      api_key_env: OPENAI_API_KEY
      model: tts-1-hd
      voice_map:            # opcional: mapeia narrador → voz OpenAI
        pt-BR-AntonioNeural: onyx
        pt-BR-ThalitaMultilingualNeural: nova
        pt-BR-FranciscaNeural: shimmer

No config de narradores, mantenha o campo voice com o nome da voz OpenAI desejada
ou use voice_map para converter automaticamente nomes edge-tts → OpenAI.
"""

import asyncio
import os

from . import rate_to_speed


class OpenAIProvider:
    def __init__(self, config: dict):
        self._config = config or {}
        self._model = self._config.get("model", "tts-1-hd")
        env_var = self._config.get("api_key_env", "OPENAI_API_KEY")
        self._api_key = os.getenv(env_var)
        self._voice_map = self._config.get("voice_map") or {}

    def _resolve_voice(self, voice: str) -> str:
        return self._voice_map.get(voice, voice)

    async def synthesize(self, text: str, voice: str, output_path: str, rate: str = "+0%") -> None:
        try:
            import openai
        except ImportError:
            raise RuntimeError("Provider OpenAI requer: pip install openai")

        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY não encontrada no ambiente.")

        resolved = self._resolve_voice(voice)
        speed = rate_to_speed(rate)

        def _sync():
            client = openai.OpenAI(api_key=self._api_key)
            response = client.audio.speech.create(
                model=self._model,
                voice=resolved,
                input=text,
                speed=speed,
                response_format="mp3",
            )
            with open(output_path, "wb") as f:
                f.write(response.content)

        await asyncio.to_thread(_sync)
