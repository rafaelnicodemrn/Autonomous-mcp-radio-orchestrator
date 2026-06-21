# src/weather.py
# Clima de Medianeira, PR e cotação USD/BRL para o cabeçalho do briefing matinal.
# APIs gratuitas, sem necessidade de chave: Open-Meteo e AwesomeAPI.
import logging

import requests

logger = logging.getLogger(__name__)

MEDIANEIRA_LAT = -25.2978
MEDIANEIRA_LON = -53.9558

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
AWESOMEAPI_URL = "https://economia.awesomeapi.com.br/last/USD-BRL"

REQUEST_TIMEOUT = 10

# https://open-meteo.com/en/docs#weathervariables (campo weather_code, WMO)
_WEATHER_CODE_DESCRICAO = {
    0: "céu limpo",
    1: "poucas nuvens",
    2: "parcialmente nublado",
    3: "nublado",
    45: "neblina",
    48: "neblina com geada",
    51: "chuvisco leve",
    53: "chuvisco moderado",
    55: "chuvisco forte",
    61: "chuva leve",
    63: "chuva moderada",
    65: "chuva forte",
    71: "neve leve",
    73: "neve moderada",
    75: "neve forte",
    80: "aguaceiros leves",
    81: "aguaceiros moderados",
    82: "aguaceiros fortes",
    95: "trovoadas",
    96: "trovoadas com granizo leve",
    99: "trovoadas com granizo forte",
}


def _weather_emoji(code: int) -> str:
    if code == 0:
        return "☀️"
    if code in (1, 2):
        return "🌤️"
    if code == 3:
        return "☁️"
    if code in (45, 48):
        return "🌫️"
    if code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        return "🌧️"
    if code in (71, 73, 75):
        return "❄️"
    if code in (95, 96, 99):
        return "⛈️"
    return "🌡️"


def get_weather_summary() -> str:
    """
    Retorna um resumo curto do clima de Medianeira, PR via Open-Meteo
    (ex: "🌤️ 24°C, parcialmente nublado"). Retorna string vazia em caso de
    falha — nunca deve bloquear o envio do briefing.
    """
    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": MEDIANEIRA_LAT,
                "longitude": MEDIANEIRA_LON,
                "current": "temperature_2m,weather_code",
                "timezone": "America/Sao_Paulo",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})
        temp = current.get("temperature_2m")
        code = current.get("weather_code")
        if temp is None or code is None:
            return ""

        descricao = _WEATHER_CODE_DESCRICAO.get(int(code), "tempo variável")
        emoji = _weather_emoji(int(code))
        return f"{emoji} {round(temp)}°C, {descricao} em Medianeira"
    except Exception:
        logger.warning("[weather] não foi possível obter o clima", exc_info=True)
        return ""


def get_exchange_rate() -> str:
    """
    Retorna a cotação USD/BRL via AwesomeAPI (ex: "💵 USD/BRL: R$ 5,42").
    Retorna string vazia em caso de falha.
    """
    try:
        resp = requests.get(AWESOMEAPI_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("USDBRL", {})
        bid = data.get("bid")
        if bid is None:
            return ""

        valor = float(bid)
        valor_fmt = f"{valor:.2f}".replace(".", ",")
        return f"💵 USD/BRL: R$ {valor_fmt}"
    except Exception:
        logger.warning("[weather] não foi possível obter a cotação USD/BRL", exc_info=True)
        return ""
