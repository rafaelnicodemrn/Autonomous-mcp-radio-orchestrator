import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

import edge_tts
import requests
from pydub import AudioSegment

PAUSE_SAME_MS = 150
PAUSE_DIFF_MS = 500

LOTTERY_NAMES = {
    "megasena": "Mega-Sena",
    "lotofacil": "Lotofácil",
    "quina": "Quina",
    "lotomania": "Lotomania",
    "timemania": "Timemania",
    "duplasena": "Dupla Sena",
    "diadesorte": "Dia de Sorte",
}

_MONTHS_PT = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]

_WEEKDAYS_PT = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]

_TEAM_PT = {
    "Brazil": "Brasil",
    "Germany": "Alemanha",
    "France": "França",
    "Spain": "Espanha",
    "England": "Inglaterra",
    "Italy": "Itália",
    "Netherlands": "Holanda",
    "Portugal": "Portugal",
    "Argentina": "Argentina",
    "Uruguay": "Uruguai",
    "Mexico": "México",
    "United States": "Estados Unidos",
    "Japan": "Japão",
    "South Korea": "Coreia do Sul",
    "Morocco": "Marrocos",
    "Senegal": "Senegal",
    "Australia": "Austrália",
    "Switzerland": "Suíça",
    "Belgium": "Bélgica",
    "Croatia": "Croácia",
    "Serbia": "Sérvia",
    "Poland": "Polônia",
    "Denmark": "Dinamarca",
    "Austria": "Áustria",
    "Ecuador": "Equador",
    "Colombia": "Colômbia",
    "Chile": "Chile",
    "Peru": "Peru",
    "Venezuela": "Venezuela",
    "Bolivia": "Bolívia",
    "Paraguay": "Paraguai",
    "Canada": "Canadá",
    "Saudi Arabia": "Arábia Saudita",
    "Iran": "Irã",
    "Qatar": "Catar",
    "Tunisia": "Tunísia",
    "Cameroon": "Camarões",
    "Ghana": "Gana",
    "Nigeria": "Nigéria",
    "Côte d'Ivoire": "Costa do Marfim",
    "Ivory Coast": "Costa do Marfim",
    "Egypt": "Egito",
    "Algeria": "Argélia",
    "Wales": "País de Gales",
    "Scotland": "Escócia",
    "Turkey": "Turquia",
    "Ukraine": "Ucrânia",
    "Czech Republic": "República Tcheca",
    "Slovakia": "Eslováquia",
    "Romania": "Romênia",
    "Panama": "Panamá",
    "Costa Rica": "Costa Rica",
    "Honduras": "Honduras",
    "Jamaica": "Jamaica",
    "New Zealand": "Nova Zelândia",
    "China": "China",
    "Indonesia": "Indonésia",
}

BRT = timezone(timedelta(hours=-3))


def fetch(source_config: dict, credentials=None) -> list[dict]:
    return []  # bypasses normal pipeline


# ── Data fetchers ────────────────────────────────────────────────────────────


def _get_weather(city: str, api_key: str) -> dict | None:
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": "metric", "lang": "pt_br"},
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        return {
            "city": d.get("name", city),
            "temp": round(d["main"]["temp"]),
            "temp_min": round(d["main"]["temp_min"]),
            "temp_max": round(d["main"]["temp_max"]),
            "feels_like": round(d["main"]["feels_like"]),
            "description": d["weather"][0]["description"],
            "humidity": d["main"]["humidity"],
        }
    except Exception as e:
        print(f"  [clima] {e}")
        return None


def _get_forecast(city: str, api_key: str, days: int) -> list[dict]:
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"q": city, "appid": api_key, "units": "metric", "lang": "pt_br", "cnt": 40},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        city_name = data.get("city", {}).get("name", city)

        daily: dict[str, list] = {}
        for entry in data.get("list", []):
            daily.setdefault(entry["dt_txt"][:10], []).append(entry)

        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        result = []

        for date_str in sorted(daily.keys()):
            if date_str == today or len(result) >= days:
                continue
            entries = daily[date_str]
            temp_min = round(min(e["main"]["temp_min"] for e in entries))
            temp_max = round(max(e["main"]["temp_max"] for e in entries))
            rain_prob = round(max(e.get("pop", 0) for e in entries) * 100)
            midday = next(
                (e for e in entries if "12:00:00" in e["dt_txt"]), entries[len(entries) // 2]
            )
            desc = midday["weather"][0]["description"]
            weekday = _WEEKDAYS_PT[datetime.strptime(date_str, "%Y-%m-%d").weekday()]
            result.append(
                {
                    "city": city_name,
                    "label": "amanhã" if date_str == tomorrow else weekday,
                    "weekday": weekday,
                    "desc": desc,
                    "temp_min": temp_min,
                    "temp_max": temp_max,
                    "rain_prob": rain_prob,
                }
            )

        return result
    except Exception as e:
        print(f"  [previsao/{city}] {e}")
        return []


def _get_finance(pairs: list[str]) -> list[dict]:
    try:
        resp = requests.get(
            f"https://economia.awesomeapi.com.br/json/last/{','.join(pairs)}", timeout=10
        )
        resp.raise_for_status()
        results = []
        for val in resp.json().values():
            results.append(
                {
                    "pair": f"{val['code']}-{val['codein']}",
                    "code": val["code"],
                    "bid": float(val["bid"]),
                    "pct_change": float(val["pctChange"]),
                }
            )
        return results
    except Exception as e:
        print(f"  [financas] {e}")
        return []


# ── Ibovespa fetcher ─────────────────────────────────────────────────────────

BRAPI_LIST = "https://brapi.dev/api/quote/list"


def _fmt_pontos(value: float) -> str:
    if value >= 1_000:
        k = value / 1_000
        return f"{k:.1f} mil pontos".replace(".", " vírgula ")
    return f"{round(value)} pontos"


def _get_ibovespa(top_n: int = 3) -> dict:
    try:
        # Índice Ibovespa
        ibov_resp = requests.get(BRAPI_LIST, params={"search": "ibovespa"}, timeout=10)
        ibov_resp.raise_for_status()
        ibov_stocks = ibov_resp.json().get("stocks", [])
        ibov = next((s for s in ibov_stocks if s["stock"] == "IBOV11"), None)

        # Top movers — filtra fracionárias (sufixo F) e volume baixo
        def _movers(order: str) -> list[dict]:
            r = requests.get(
                BRAPI_LIST,
                params={
                    "sortBy": "change",
                    "sortOrder": order,
                    "limit": 40,
                    "type": "stock",
                },
                timeout=10,
            )
            r.raise_for_status()
            stocks = r.json().get("stocks", [])
            filtered = [
                s
                for s in stocks
                if not s["stock"].endswith("F")
                and (s.get("volume") or 0) > 200_000
                and s.get("change") is not None
            ]
            return filtered[:top_n]

        altas = _movers("desc")
        baixas = _movers("asc")

        result = {
            "pontos": round(ibov["close"]) if ibov else None,
            "change": round(ibov["change"], 2) if ibov else None,
            "altas": [{"ticker": s["stock"], "change": round(s["change"], 2)} for s in altas],
            "baixas": [{"ticker": s["stock"], "change": round(s["change"], 2)} for s in baixas],
        }

        if result["pontos"]:
            print(f"  Ibovespa: {result['pontos']:,} pts ({result['change']:+.2f}%)")
        for s in altas:
            print(f"  Alta  {s['stock']:8} {s['change']:+.2f}%")
        for s in baixas:
            print(f"  Baixa {s['stock']:8} {s['change']:+.2f}%")

        return result

    except Exception as e:
        print(f"  [ibovespa] {e}")
        return {}


# ── Lottery fetcher ──────────────────────────────────────────────────────────


def _fmt_date_pt(date_str: str) -> str:
    try:
        day, month, _ = date_str.split("/")
        return f"{int(day)} de {_MONTHS_PT[int(month) - 1]}"
    except Exception:
        return date_str


def _fmt_prize(value: float) -> str:
    if value >= 1_000_000:
        m = value / 1_000_000
        if m == round(m):
            return f"{round(m)} milhões de reais"
        return f"{m:.1f} milhões de reais".replace(".", " vírgula ")
    if value >= 1_000:
        return f"{round(value / 1_000)} mil reais"
    return f"{round(value)} reais"


def _fmt_dezenas(dezenas: list[str]) -> str:
    return ", ".join(str(int(d)) for d in dezenas)


def _get_sun_times(lat: float, lng: float, tzid: str) -> dict | None:
    try:
        resp = requests.get(
            "https://api.sunrise-sunset.org/json",
            params={"lat": lat, "lng": lng, "tzid": tzid, "formatted": 0},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            return None
        r = data["results"]
        sunrise = datetime.fromisoformat(r["sunrise"]).strftime("%H:%M")
        sunset = datetime.fromisoformat(r["sunset"]).strftime("%H:%M")
        secs = int(r.get("day_length", 0))
        print(
            f"  Sol: nasce {sunrise} / se põe {sunset} "
            f"({secs // 3600}h{(secs % 3600) // 60:02d}min de luz)"
        )
        return {
            "sunrise": sunrise,
            "sunset": sunset,
            "day_length_h": secs // 3600,
            "day_length_m": (secs % 3600) // 60,
        }
    except Exception as e:
        print(f"  [sol] {e}")
        return None


def _get_lottery(games: list[str]) -> list[dict]:
    results = []
    for game in games:
        try:
            resp = requests.get(
                f"https://servicebus2.caixa.gov.br/portaldeloterias/api/{game}",
                timeout=10,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            top = data.get("listaRateioPremio", [{}])[0]
            entry = {
                "game": game,
                "name": LOTTERY_NAMES.get(game, game.title()),
                "numero": data.get("numero", ""),
                "data": _fmt_date_pt(data.get("dataApuracao", "")),
                "dezenas": _fmt_dezenas(data.get("listaDezenas", [])),
                "acumulado": data.get("acumulado", False),
                "ganhadores": top.get("numeroDeGanhadores", 0),
                "valor_premio": top.get("valorPremio", 0.0),
                "proximo_valor": data.get("valorEstimadoProximoConcurso", 0.0),
                "proxima_data": _fmt_date_pt(data.get("dataProximoConcurso", "")),
            }
            results.append(entry)
            print(f"  {entry['name']}: concurso {entry['numero']}, {data.get('dataApuracao')}")
        except Exception as e:
            print(f"  [loteria/{game}] {e}")
    return results


# ── Football fetcher ─────────────────────────────────────────────────────────


def _team_pt(name: str) -> str:
    return _TEAM_PT.get(name, name)


def _get_football(competition: str, api_key: str) -> dict:
    now_brt = datetime.now(BRT)
    today_brt = now_brt.date()
    yesterday_brt = today_brt - timedelta(days=1)
    tomorrow_brt = today_brt + timedelta(days=1)

    try:
        resp = requests.get(
            f"https://api.football-data.org/v4/competitions/{competition}/matches",
            params={"dateFrom": str(yesterday_brt), "dateTo": str(tomorrow_brt)},
            headers={"X-Auth-Token": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [futebol] {e}")
        return {}

    comp_name = data.get("competition", {}).get("name", "Copa do Mundo")
    finished, today_games, live = [], [], []

    for m in data.get("matches", []):
        status = m.get("status", "")
        brt_dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(BRT)
        home = _team_pt(m["homeTeam"].get("name", ""))
        away = _team_pt(m["awayTeam"].get("name", ""))
        ft = m.get("score", {}).get("fullTime", {})
        hs, as_ = ft.get("home"), ft.get("away")
        entry = {
            "home": home,
            "away": away,
            "home_score": hs,
            "away_score": as_,
            "time": brt_dt.strftime("%H:%M"),
        }

        if status == "FINISHED" and brt_dt.date() == yesterday_brt:
            finished.append(entry)
            print(f"  [futebol] {home} {hs}x{as_} {away}")
        elif status in ("SCHEDULED", "TIMED") and brt_dt.date() == today_brt:
            today_games.append(entry)
            print(f"  [futebol] Hoje {brt_dt.strftime('%H:%M')}: {home} x {away}")
        elif status == "IN_PLAY":
            live.append(entry)
            print(f"  [futebol] AO VIVO: {home} {hs}x{as_} {away}")

    return {"name": comp_name, "finished": finished, "today": today_games, "live": live}


# ── Script builder ───────────────────────────────────────────────────────────


def _pct(pct: float) -> str:
    if pct > 0.05:
        return f"em alta de {pct:.1f} por cento"
    if pct < -0.05:
        return f"em queda de {abs(pct):.1f} por cento"
    return "estavel"


def _build_lines(
    weather_list: list[dict],
    forecast: list[dict],
    finance: list[dict],
    lottery: list[dict],
    football: dict,
    ibovespa: dict,
    narrators: list[dict],
    source_name: str,
    is_first_of_day: bool,
    sun: dict | None = None,
    station_name: str = "RadioIA",
) -> list[dict]:
    A = "LOCUTOR_A"
    B = "LOCUTOR_B" if len(narrators) > 1 else "LOCUTOR_A"

    lines = []

    if is_first_of_day:
        lines.append({"locutor": A, "text": f"Bom dia! Agora o {source_name}."})
    else:
        lines.append({"locutor": A, "text": f"Agora o {source_name} aqui na {station_name}."})

    locutores = [A, B]
    for i, weather in enumerate(weather_list):
        loc = locutores[i % 2]
        loc2 = locutores[(i + 1) % 2]
        city = weather["city"]
        desc = weather["description"]
        temp = weather["temp"]
        tmin = weather["temp_min"]
        tmax = weather["temp_max"]
        feels = weather["feels_like"]
        hum = weather["humidity"]
        lines.append(
            {
                "locutor": loc,
                "text": f"Clima em {city}: {desc}, {temp} graus, sensacao termica de {feels}.",
            }
        )
        lines.append(
            {
                "locutor": loc2,
                "text": f"Minima de {tmin}, maxima de {tmax} graus. Umidade em {hum} por cento.",
            }
        )

    if forecast:
        by_city: dict[str, list] = {}
        for day in forecast:
            by_city.setdefault(day["city"], []).append(day)
        for city, days in by_city.items():
            lines.append({"locutor": A, "text": f"Previsão para {city}:"})
            for i, day in enumerate(days):
                rain_txt = (
                    f" Chance de chuva de {day['rain_prob']} por cento."
                    if day["rain_prob"] >= 30
                    else ""
                )
                lines.append(
                    {
                        "locutor": locutores[i % 2],
                        "text": f"{day['label'].capitalize()}: {day['desc']}, "
                        f"mínima de {day['temp_min']}, máxima de "
                        f"{day['temp_max']} graus.{rain_txt}",
                    }
                )

    if sun:
        lines.append(
            {
                "locutor": B,
                "text": f"O sol nasce às {sun['sunrise']} e se põe às {sun['sunset']}. "
                f"São {sun['day_length_h']} horas e {sun['day_length_m']} minutos de luz hoje.",
            }
        )

    if ibovespa:
        pontos = ibovespa.get("pontos")
        change = ibovespa.get("change")
        altas = ibovespa.get("altas", [])
        baixas = ibovespa.get("baixas", [])

        if pontos:
            direcao = "em alta" if change >= 0 else "em queda"
            pct = f"{abs(change):.1f}".replace(".", " vírgula ")
            lines.append(
                {
                    "locutor": A,
                    "text": f"Bolsa de valores. O Ibovespa opera {direcao}, "
                    f"aos {_fmt_pontos(pontos)}, variação de {pct} por cento.",
                }
            )
        if altas:
            tickers = ", ".join(s["ticker"] for s in altas)
            pcts = ", ".join(f"{s['change']:+.1f}%".replace(".", ",") for s in altas)
            lines.append(
                {"locutor": B, "text": f"Entre as maiores altas: {tickers}, com ganhos de {pcts}."}
            )
        if baixas:
            tickers = ", ".join(s["ticker"] for s in baixas)
            pcts = ", ".join(f"{abs(s['change']):.1f}%".replace(".", ",") for s in baixas)
            lines.append(
                {"locutor": A, "text": f"Nas maiores baixas: {tickers}, com quedas de {pcts}."}
            )

    if finance:
        lines.append({"locutor": B, "text": "Agora as cotacoes do momento."})
        for item in finance:
            bid = item["bid"]
            pct = _pct(item["pct_change"])
            code = item["code"]
            if code == "USD":
                lines.append({"locutor": A, "text": f"Dolar americano a R$ {bid:.2f}, {pct}."})
            elif code == "EUR":
                lines.append({"locutor": B, "text": f"Euro a R$ {bid:.2f}, {pct}."})
            elif code == "BTC":
                btc = bid / 1000
                lines.append({"locutor": A, "text": f"Bitcoin cotado a R$ {btc:.1f} mil, {pct}."})
            else:
                lines.append({"locutor": B, "text": f"{code} a R$ {bid:.2f}, {pct}."})

    if lottery:
        if weather_list or finance or ibovespa or football:
            lines.append({"locutor": A, "text": "Agora os resultados das loterias."})
        for lot in lottery:
            lines.append(
                {
                    "locutor": A,
                    "text": f"{lot['name']}, concurso {lot['numero']}, "
                    f"sorteio do dia {lot['data']}. "
                    f"Dezenas: {lot['dezenas']}.",
                }
            )
            if lot["acumulado"] or lot["ganhadores"] == 0:
                prox = _fmt_prize(lot["proximo_valor"])
                lines.append(
                    {
                        "locutor": B,
                        "text": f"Acumulou! Próximo sorteio no dia {lot['proxima_data']}, "
                        f"com prêmio estimado de {prox}.",
                    }
                )
            else:
                g = lot["ganhadores"]
                ganhador_txt = "Um apostador acertou" if g == 1 else f"{g} apostadores acertaram"
                lines.append(
                    {
                        "locutor": B,
                        "text": (
                            f"{ganhador_txt} e cada ganhador levou "
                            f"{_fmt_prize(lot['valor_premio'])}."
                        ),
                    }
                )
                if lot["proximo_valor"] > 0:
                    lines.append(
                        {
                            "locutor": A,
                            "text": f"Próximo sorteio no dia {lot['proxima_data']}, "
                            f"prêmio estimado de {_fmt_prize(lot['proximo_valor'])}.",
                        }
                    )

    if football:
        comp = football.get("name", "Copa do Mundo")
        live = football.get("live", [])
        done = football.get("finished", [])
        today = football.get("today", [])

        if live:
            lines.append({"locutor": A, "text": f"Atenção! Jogos ao vivo agora na {comp}!"})
            for i, m in enumerate(live):
                score = (
                    f"{m['home_score']} a {m['away_score']}"
                    if m["home_score"] is not None
                    else "em andamento"
                )
                lines.append(
                    {"locutor": locutores[i % 2], "text": f"{m['home']} e {m['away']}, {score}."}
                )

        if done:
            lines.append({"locutor": A, "text": f"Resultados de ontem na {comp}."})
            for i, m in enumerate(done):
                hs, as_ = m["home_score"], m["away_score"]
                if hs == as_:
                    result = f"empate em {hs} a {as_}"
                elif hs > as_:
                    result = f"{m['home']} venceu por {hs} a {as_}"
                else:
                    result = f"{m['away']} venceu por {as_} a {hs}"
                lines.append(
                    {
                        "locutor": locutores[i % 2],
                        "text": f"{m['home']} contra {m['away']}: {result}.",
                    }
                )

        if today:
            lines.append({"locutor": B, "text": f"Jogos de hoje na {comp}."})
            for i, m in enumerate(today):
                lines.append(
                    {
                        "locutor": locutores[i % 2],
                        "text": f"Às {m['time']}, {m['home']} enfrenta {m['away']}.",
                    }
                )

    lines.append(
        {
            "locutor": B,
            "text": "Essas sao as informacoes do momento. Continuamos com mais programacao.",
        }
    )
    return lines


# ── Audio generation ─────────────────────────────────────────────────────────


async def _generate_all(lines: list[dict], voices: dict, temp_dir: str) -> list[str]:
    paths = [os.path.join(temp_dir, f"line_{i:04d}.mp3") for i in range(len(lines))]
    for line, path in zip(lines, paths):
        voice = voices.get(line["locutor"], next(iter(voices.values())))
        communicate = edge_tts.Communicate(line["text"], voice)
        await communicate.save(path)
        await asyncio.sleep(0.1)
    return paths


def generate_episode(
    source_config: dict,
    output_dir: str,
    narrators: list[dict],
    is_first_of_day: bool = False,
    station_name: str = "RadioIA",
) -> int:
    settings = source_config.get("settings", {})
    source_name = source_config.get("name", "Resumo do Dia")

    # Weather + Forecast
    weather_list = []
    forecast = []
    wcfg = settings.get("weather", {})
    if wcfg.get("enabled", True):
        api_key = os.getenv(wcfg.get("api_key_env", "OPENWEATHER_API_KEY"), "")
        cities = wcfg.get("cities") or ([wcfg["city"]] if wcfg.get("city") else ["Sao Paulo"])
        forecast_days = wcfg.get("forecast_days", 0)
        if api_key:
            for city in cities:
                w = _get_weather(city, api_key)
                if w:
                    weather_list.append(w)
                    print(f"  Clima {w['city']}: {w['description']}, {w['temp']}°C")
            if forecast_days > 0:
                for city in cities:
                    forecast.extend(_get_forecast(city, api_key, forecast_days))
                    print(f"  Previsão {city}: {forecast_days} dia(s)")
        else:
            print("  [clima] OPENWEATHER_API_KEY nao encontrada — pulando.")

    # Finance
    finance = []
    fcfg = settings.get("finance", {})
    if fcfg.get("enabled", True):
        pairs = fcfg.get("pairs", ["USD-BRL", "EUR-BRL", "BTC-BRL"])
        finance = _get_finance(pairs)
        for item in finance:
            print(f"  {item['pair']}: R$ {item['bid']:.2f} ({_pct(item['pct_change'])})")

    # Lottery
    lottery = []
    lcfg = settings.get("lottery", {})
    if lcfg.get("enabled", False):
        games = lcfg.get("games", ["megasena", "lotofacil"])
        lottery = _get_lottery(games)

    # Football
    football = {}
    ftcfg = settings.get("football", {})
    if ftcfg.get("enabled", False):
        ft_key = os.getenv(ftcfg.get("api_key_env", "FOOTBALL_DATA_API_KEY"), "")
        comp_code = ftcfg.get("competition", "WC")
        if ft_key:
            football = _get_football(comp_code, ft_key)
        else:
            print("  [futebol] FOOTBALL_DATA_API_KEY nao encontrada — pulando.")

    # Ibovespa
    ibovespa = {}
    icfg = settings.get("ibovespa", {})
    if icfg.get("enabled", False):
        top_n = icfg.get("top_movers", 3)
        ibovespa = _get_ibovespa(top_n)

    # Nascer e pôr do sol
    sun = None
    scfg = settings.get("sun", {})
    if scfg.get("enabled", False):
        lat = scfg.get("lat")
        lng = scfg.get("lng")
        tzid = scfg.get("tzid", "America/Sao_Paulo")
        if lat is not None and lng is not None:
            sun = _get_sun_times(lat, lng, tzid)
        else:
            print("  [sol] lat/lng nao configurados — pulando.")

    if (
        not weather_list
        and not finance
        and not lottery
        and not football
        and not ibovespa
        and not sun
    ):
        raise RuntimeError("Nenhum dado disponivel para gerar o episodio.")

    active = narrators[:2]
    lines = _build_lines(
        weather_list,
        forecast,
        finance,
        lottery,
        football,
        ibovespa,
        active,
        source_name,
        is_first_of_day,
        sun,
        station_name,
    )

    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    keys = ["LOCUTOR_A", "LOCUTOR_B"]
    voices = {keys[i]: n["voice"] for i, n in enumerate(active)}

    audio_files = asyncio.run(_generate_all(lines, voices, temp_dir))

    combined = AudioSegment.empty()
    for i, (path, line) in enumerate(zip(audio_files, lines)):
        combined += AudioSegment.from_mp3(path)
        if i < len(lines) - 1:
            pause = PAUSE_DIFF_MS if lines[i + 1]["locutor"] != line["locutor"] else PAUSE_SAME_MS
            combined += AudioSegment.silent(pause)

    episode_path = os.path.join(output_dir, "episode.mp3")
    combined.export(
        episode_path,
        format="mp3",
        bitrate="128k",
        tags={"title": source_name, "artist": station_name},
    )

    shutil.rmtree(temp_dir)
    duration = round(len(combined) / 1000)

    # Notes for web player
    notes = []
    if sun:
        notes.append(
            {
                "title": f"Sol — nasce {sun['sunrise']} / se põe {sun['sunset']}",
                "channel": f"{sun['day_length_h']}h{sun['day_length_m']:02d}min de luz",
                "url": "https://sunrise-sunset.org",
                "views": 0,
                "published_at": "",
                "top_comments": [],
            }
        )
    if weather_list:
        for w in weather_list:
            notes.append(
                {
                    "title": f"Clima em {w['city']}",
                    "channel": f"{w['description'].capitalize()} · {w['temp']}°C "
                    f"(min {w['temp_min']}° / max {w['temp_max']}°) · "
                    f"Umidade {w['humidity']}%",
                    "url": "",
                    "views": 0,
                    "published_at": "",
                    "top_comments": [],
                }
            )
    for day in forecast:
        rain_txt = f" · Chuva {day['rain_prob']}%" if day["rain_prob"] >= 30 else ""
        notes.append(
            {
                "title": f"Previsão {day['city']} — {day['label'].capitalize()}",
                "channel": (
                    f"{day['desc'].capitalize()} · {day['temp_min']}°/"
                    f"{day['temp_max']}°{rain_txt}"
                ),
                "url": "",
                "views": 0,
                "published_at": "",
                "top_comments": [],
            }
        )
    if ibovespa.get("pontos"):
        pct = ibovespa.get("change", 0)
        notes.append(
            {
                "title": f"Ibovespa: {ibovespa['pontos']:,} pts",
                "channel": f"{'Alta' if pct >= 0 else 'Baixa'} de {abs(pct):.2f}%",
                "url": "",
                "views": 0,
                "published_at": "",
                "top_comments": [],
            }
        )
    for m in football.get("finished", []) + football.get("today", []) + football.get("live", []):
        hs, as_ = m.get("home_score"), m.get("away_score")
        score_txt = f"{hs} x {as_}" if hs is not None else "a jogar"
        notes.append(
            {
                "title": f"{m['home']} x {m['away']}",
                "channel": f"{football.get('name','Copa')} · {score_txt}",
                "url": "",
                "views": 0,
                "published_at": "",
                "top_comments": [],
            }
        )
    for item in finance:
        notes.append(
            {
                "title": f"{item['pair']}: R$ {item['bid']:.2f}",
                "channel": _pct(item["pct_change"]).capitalize(),
                "url": "",
                "views": 0,
                "published_at": "",
                "top_comments": [],
            }
        )
    for lot in lottery:
        status = "Acumulou" if lot["acumulado"] else f"{lot['ganhadores']} ganhador(es)"
        notes.append(
            {
                "title": f"{lot['name']} — Concurso {lot['numero']}",
                "channel": f"{lot['dezenas']} · {status}",
                "url": "",
                "views": 0,
                "published_at": "",
                "top_comments": [],
            }
        )

    meta = {
        "source_name": source_name,
        "duration_seconds": duration,
        "videos_covered": len(notes),
        "links": notes,
    }
    with open(os.path.join(output_dir, "episode.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return duration
