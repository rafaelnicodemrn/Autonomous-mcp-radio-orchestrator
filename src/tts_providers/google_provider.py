"""Provider Google Cloud TTS — requer: pip install google-cloud-texttospeech
Vozes pt-BR recomendadas (Studio = maior qualidade):
  pt-BR-Studio-B (Male) | pt-BR-Studio-C (Female)
  pt-BR-Neural2-A (Female) | pt-BR-Neural2-B (Male) | pt-BR-Neural2-C (Female)
  pt-BR-Wavenet-A (Female) | pt-BR-Wavenet-B (Male) | pt-BR-Wavenet-C (Female)

Configuração em config.yaml:
  tts:
    provider: google
    google:
      credentials_env: GOOGLE_APPLICATION_CREDENTIALS  # path do service account JSON
      language_code: pt-BR
      voice_map:                    # opcional: mapeia nome edge-tts → nome Google
        pt-BR-AntonioNeural: pt-BR-Studio-B
        pt-BR-ThalitaMultilingualNeural: pt-BR-Studio-C
        pt-BR-FranciscaNeural: pt-BR-Neural2-C

Obtenha credenciais em: https://console.cloud.google.com/apis/credentials
"""

import asyncio
import os

from . import rate_to_speed


class GoogleProvider:
    def __init__(self, config: dict):
        self._config = config or {}
        self._lang = self._config.get("language_code", "pt-BR")
        self._voice_map = self._config.get("voice_map") or {}
        env_var = self._config.get("credentials_env", "GOOGLE_APPLICATION_CREDENTIALS")
        creds = os.getenv(env_var)
        if creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds

    def _resolve_voice(self, voice: str) -> str:
        return self._voice_map.get(voice, voice)

    async def synthesize(self, text: str, voice: str, output_path: str, rate: str = "+0%") -> None:
        try:
            from google.cloud import texttospeech
        except ImportError:
            raise RuntimeError("Provider Google requer: pip install google-cloud-texttospeech")

        resolved = self._resolve_voice(voice)
        speed = rate_to_speed(rate)

        def _sync():
            client = texttospeech.TextToSpeechClient()
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    name=resolved,
                    language_code=self._lang,
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=speed,
                ),
            )
            with open(output_path, "wb") as f:
                f.write(response.audio_content)

        await asyncio.to_thread(_sync)
