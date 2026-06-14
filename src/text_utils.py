"""Utilitários de normalização de texto para leitura em TTS."""

import re

# ── Moeda ─────────────────────────────────────────────────────────────────────

_CURRENCY_RE = re.compile(r"R\$\s*([\d.]+(?:,\d{2})?)")


def _currency_to_words(match: re.Match) -> str:
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        int_val = int(float(raw))
    except ValueError:
        return match.group(0)

    if int_val == 0:
        return "zero reais"

    millions = int_val // 1_000_000
    remainder = int_val % 1_000_000
    thousands = remainder // 1_000
    rest = remainder % 1_000

    parts = []
    if millions:
        parts.append(f"{millions} {'milhão' if millions == 1 else 'milhões'}")
    if thousands:
        parts.append(f"{thousands} mil")
    if rest:
        parts.append(str(rest))

    text = " e ".join(parts)

    # "de reais" após milhão(ões) quando não há complemento
    if millions and not thousands and not rest:
        return text + " de reais"
    return text + " reais"


# ── API pública ───────────────────────────────────────────────────────────────


def normalize_for_tts(text: str) -> str:
    """Converte expressões problemáticas para leitura em TTS.

    Atualmente normaliza:
    - Valores em reais: "R$ 3.000,00" → "3 mil reais"
    """
    text = _CURRENCY_RE.sub(_currency_to_words, text)
    return text
