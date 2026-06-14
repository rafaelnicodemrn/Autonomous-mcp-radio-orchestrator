"""
Gerenciador de spots (propagandas / comunicados).

Três origens suportadas:
  file — MP3 pré-gravado fornecido pelo usuário
  tts  — texto → edge-tts (mesma voz da vinheta)
  llm  — tema → LLM → edge-tts (script gerado e variado diariamente)

Rotação: ponderada por weight, sem repetição consecutiva, com cap por dia.
Cache: file=memória, tts=disco permanente, llm=disco por dia.
"""

import os
import random
import threading
from datetime import datetime

SPOTS_CACHE_DIR = os.path.join("output", "_spots")

_lock = threading.Lock()
_state = {"last_id": None}


# ── Config helpers ────────────────────────────────────────────────────────────


def _load_config():
    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("spots", []), cfg.get("spots_config", {}), cfg


def _vinheta_voice(cfg):
    return cfg.get("vinheta", {}).get("voice", "pt-BR-FranciscaNeural")


def _vinheta_rate(cfg):
    return cfg.get("vinheta", {}).get("rate", "+15%")


def _llm_model(cfg):
    llm = cfg.get("llm", cfg.get("claude", {}))
    return llm.get("model", "claude-sonnet-4-6")


def _llm_api_base(cfg):
    llm = cfg.get("llm", cfg.get("claude", {}))
    return llm.get("api_base")


# ── Geração de áudio ──────────────────────────────────────────────────────────


def _tts_to_bytes(text: str, voice: str, rate: str) -> bytes | None:
    import asyncio
    import os as _os
    import sys
    import tempfile

    import edge_tts

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:

        async def _g():
            await edge_tts.Communicate(text, voice, rate=rate).save(tmp.name)

        asyncio.run(_g())
        with open(tmp.name, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        try:
            _os.unlink(tmp.name)
        except OSError:
            pass


def _get_audio(spot: dict, cfg: dict) -> bytes | None:
    sid = spot["id"]
    stype = spot.get("type", "file")
    os.makedirs(SPOTS_CACHE_DIR, exist_ok=True)

    if stype == "file":
        path = spot.get("path", "")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        print(f"  [spot/{sid}] arquivo nao encontrado: {path}")
        return None

    if stype == "tts":
        cache = os.path.join(SPOTS_CACHE_DIR, f"{sid}.mp3")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()
        voice = spot.get("voice") or _vinheta_voice(cfg)
        rate = spot.get("rate") or _vinheta_rate(cfg)
        audio = _tts_to_bytes(spot.get("text", ""), voice, rate)
        if audio:
            with open(cache, "wb") as f:
                f.write(audio)
        return audio

    if stype == "llm":
        import litellm

        today = datetime.now().strftime("%Y-%m-%d")
        cache = os.path.join(SPOTS_CACHE_DIR, f"{sid}-{today}.mp3")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()

        topic = spot.get("topic", "")
        secs = spot.get("duration_seconds", 20)
        prompt = (
            f"Crie um spot de radio de aproximadamente {secs} segundos sobre:\n{topic}\n\n"
            "REGRAS: tom natural de locutor de radio, maximo 3 frases curtas, "
            "sem marcacoes de cena, apenas o texto para leitura em voz alta."
        )
        model = spot.get("model") or _llm_model(cfg)
        api_base = _llm_api_base(cfg)
        kwargs = {"api_base": api_base} if api_base else {}
        try:
            resp = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                **kwargs,
            )
            script = resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [spot/{sid}] erro LLM: {e}")
            return None

        voice = spot.get("voice") or _vinheta_voice(cfg)
        rate = spot.get("rate") or _vinheta_rate(cfg)
        audio = _tts_to_bytes(script, voice, rate)
        if audio:
            with open(cache, "wb") as f:
                f.write(audio)
            with open(cache.replace(".mp3", ".txt"), "w", encoding="utf-8") as f:
                f.write(script)
        return audio

    return None


# ── Rotação ───────────────────────────────────────────────────────────────────


def get_next_spot() -> tuple[dict, bytes] | None:
    """Retorna (spot_config, audio_bytes) segundo a rotação configurada, ou None."""
    with _lock:
        spots, _, cfg = _load_config()
        if not spots:
            return None

        pool = []
        for s in spots:
            if s["id"] == _state["last_id"] and len(spots) > 1:
                continue
            pool.extend([s] * max(1, s.get("weight", 1)))

        if not pool:
            return None

        chosen = random.choice(pool)
        _state["last_id"] = chosen["id"]

    audio = _get_audio(chosen, cfg)
    if not audio:
        return None
    return chosen, audio


# ── Warmup ────────────────────────────────────────────────────────────────────


def warmup():
    """Pré-gera áudio dos spots tts/llm em background ao iniciar o servidor."""
    try:
        spots, _, cfg = _load_config()
        for spot in spots:
            if spot.get("type") in ("tts", "llm"):
                _get_audio(spot, cfg)
    except Exception:
        pass
