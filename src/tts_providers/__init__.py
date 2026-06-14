"""
TTS Providers — seleciona o motor de síntese de voz via config.yaml.

Configuração em config.yaml:
  tts:
    provider: edge_tts   # edge_tts (padrão) | openai | elevenlabs | google

Cada provider implementa:
  async def synthesize(text, voice, output_path, rate='+0%') -> None
"""


def get_provider(tts_config: dict):
    """Retorna a instância do provider configurado."""
    cfg = tts_config or {}
    provider = cfg.get("provider", "edge_tts")

    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(cfg.get("openai") or {})

    if provider == "elevenlabs":
        from .elevenlabs_provider import ElevenLabsProvider

        return ElevenLabsProvider(cfg.get("elevenlabs") or {})

    if provider == "google":
        from .google_provider import GoogleProvider

        return GoogleProvider(cfg.get("google") or {})

    from .edge_tts_provider import EdgeTTSProvider

    return EdgeTTSProvider(cfg.get("edge_tts") or {})


def rate_to_speed(rate: str) -> float:
    """Converte string de taxa edge-tts ('+20%') para multiplicador float (1.2).
    Usado por providers que aceitam speed como float (OpenAI, Google).
    """
    try:
        pct = float(rate.strip().replace("%", "").lstrip("+"))
        return max(0.25, min(4.0, 1.0 + pct / 100))
    except (ValueError, AttributeError):
        return 1.0
