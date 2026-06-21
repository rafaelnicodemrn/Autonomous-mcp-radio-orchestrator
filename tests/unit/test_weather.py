import requests

import src.weather as weather


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


class TestGetWeatherSummary:
    def test_retorna_resumo_formatado(self, monkeypatch):
        fake = _FakeResponse({"current": {"temperature_2m": 23.6, "weather_code": 2}})
        monkeypatch.setattr(weather.requests, "get", lambda *a, **k: fake)

        result = weather.get_weather_summary()

        assert "24°C" in result
        assert "parcialmente nublado" in result
        assert "Medianeira" in result

    def test_retorna_vazio_em_falha_de_rede(self, monkeypatch):
        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("sem rede")

        monkeypatch.setattr(weather.requests, "get", boom)

        assert weather.get_weather_summary() == ""

    def test_retorna_vazio_em_http_error(self, monkeypatch):
        fake = _FakeResponse({}, status_code=500)
        monkeypatch.setattr(weather.requests, "get", lambda *a, **k: fake)

        assert weather.get_weather_summary() == ""

    def test_retorna_vazio_quando_campos_ausentes(self, monkeypatch):
        fake = _FakeResponse({"current": {}})
        monkeypatch.setattr(weather.requests, "get", lambda *a, **k: fake)

        assert weather.get_weather_summary() == ""


class TestGetExchangeRate:
    def test_retorna_cotacao_formatada(self, monkeypatch):
        fake = _FakeResponse({"USDBRL": {"bid": "5.4231"}})
        monkeypatch.setattr(weather.requests, "get", lambda *a, **k: fake)

        result = weather.get_exchange_rate()

        assert result == "💵 USD/BRL: R$ 5,42"

    def test_retorna_vazio_em_falha_de_rede(self, monkeypatch):
        def boom(*a, **k):
            raise requests.exceptions.Timeout("timeout")

        monkeypatch.setattr(weather.requests, "get", boom)

        assert weather.get_exchange_rate() == ""

    def test_retorna_vazio_quando_bid_ausente(self, monkeypatch):
        fake = _FakeResponse({"USDBRL": {}})
        monkeypatch.setattr(weather.requests, "get", lambda *a, **k: fake)

        assert weather.get_exchange_rate() == ""
