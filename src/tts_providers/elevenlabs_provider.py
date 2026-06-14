"""Provider ElevenLabs — requer: pip install elevenlabs
Modelos recomendados: eleven_multilingual_v2 | eleven_turbo_v2_5

Configuração em config.yaml:
  tts:
    provider: elevenlabs
    elevenlabs:
      api_key_env: ELEVENLABS_API_KEY
      model: eleven_multilingual_v2
      voice_map:                     # opcional: mapeia nome edge-tts → voice_id ElevenLabs
        pt-BR-AntonioNeural: <voice_id>
        pt-BR-ThalitaMultilingualNeural: <voice_id>

No config de narradores, use o voice_id do ElevenLabs diretamente no campo voice,
ou configure voice_map para conversão automática.
Obtenha voice_ids em: https://elevenlabs.io/voice-library
"""

import asyncio
import os


class ElevenLabsProvider:
    def __init__(self, config: dict):
        self._config = config or {}
        self._model = self._config.get("model", "eleven_multilingual_v2")
        env_var = self._config.get("api_key_env", "ELEVENLABS_API_KEY")
        self._api_key = os.getenv(env_var)
        self._voice_map = self._config.get("voice_map") or {}

    def _resolve_voice(self, voice: str) -> str:
        return self._voice_map.get(voice, voice)

    async def synthesize(self, text: str, voice: str, output_path: str, rate: str = "+0%") -> None:
        try:
            import elevenlabs  # noqa: F401
        except ImportError:
            raise RuntimeError("Provider ElevenLabs requer: pip install elevenlabs")

        if not self._api_key:
            raise RuntimeError("ELEVENLABS_API_KEY não encontrada no ambiente.")

        resolved = self._resolve_voice(voice)

        def _sync():
            from elevenlabs.client import ElevenLabs

            client = ElevenLabs(api_key=self._api_key)
            audio = client.text_to_speech.convert(
                voice_id=resolved,
                text=text,
                model_id=self._model,
                output_format="mp3_44100_128",
            )
            with open(output_path, "wb") as f:
                for chunk in audio:
                    if chunk:
                        f.write(chunk)

        await asyncio.to_thread(_sync)
