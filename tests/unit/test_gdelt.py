import requests

import plugins.gdelt as gdelt


class TestGdeltFetch:
    def test_timeout_em_todas_as_queries_nao_propaga_excecao(self, monkeypatch):
        """Timeout de rede deve ser logado como warning, não derrubar o caller (main.py)."""

        def _raise_timeout(query):
            raise requests.exceptions.Timeout("Read timed out.")

        monkeypatch.setattr(gdelt, "_fetch_query", _raise_timeout)

        items = gdelt.fetch({})

        assert items == []

    def test_recupera_artigos_quando_api_responde(self, monkeypatch):
        payload = {
            "articles": [
                {
                    "title": "Noticia",
                    "url": "https://x.com/1",
                    "domain": "x.com",
                    "seendate": "2026",
                },
            ]
        }
        monkeypatch.setattr(gdelt, "_fetch_query", lambda query: payload)

        items = gdelt.fetch({})

        assert len(items) >= 1
        assert items[0]["url"] == "https://x.com/1"

    def test_param_cli_customiza_temas_buscados(self, monkeypatch):
        queries_usadas = []

        def _fake_fetch_query(query):
            queries_usadas.append(query)
            return {"articles": []}

        monkeypatch.setattr(gdelt, "_fetch_query", _fake_fetch_query)

        gdelt.fetch({"_param": "catolicismo,politica,conservadorismo"})

        assert queries_usadas == ["catolicismo", "politica", "conservadorismo"]

    def test_uma_query_falhando_nao_impede_as_demais(self, monkeypatch):
        chamadas = {"n": 0}

        def _fake_fetch_query(query):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise requests.exceptions.Timeout("Read timed out.")
            return {"articles": []}

        monkeypatch.setattr(gdelt, "_fetch_query", _fake_fetch_query)

        items = gdelt.fetch({})

        assert items == []
        assert chamadas["n"] == len(gdelt.QUERIES)
