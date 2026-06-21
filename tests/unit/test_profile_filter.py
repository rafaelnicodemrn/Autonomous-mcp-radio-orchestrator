import json

import src.profile_filter as profile_filter
import content_enricher
import adaptive_engine


class TestShouldBlock:
    def test_bloqueia_item_com_palavra_ignorada(self, sample_config):
        profile = sample_config["perfil"]
        item = {"title": "Seu horóscopo de hoje", "source_name": "g1"}
        assert profile_filter.should_block(item, profile) is True

    def test_nao_bloqueia_item_relevante(self, sample_config):
        profile = sample_config["perfil"]
        item = {"title": "Grêmio vence clássico", "source_name": "gaucha"}
        assert profile_filter.should_block(item, profile) is False


class TestScoreBatchWithGemini:
    def test_aplica_score_retornado_pelo_llm(self, sample_config, monkeypatch):
        profile = sample_config["perfil"]
        items = [
            {"title": "Notícia 1", "source_name": "g1"},
            {"title": "Notícia 2", "source_name": "g1"},
        ]
        fake_response = json.dumps([
            {"i": 1, "score": 8, "motivo": "tecnologia"},
            {"i": 2, "score": 3, "motivo": "irrelevante"},
        ])
        monkeypatch.setattr(content_enricher, "_gemini_call_with_retry", lambda *a, **k: fake_response)

        result = profile_filter.score_batch_with_gemini(items, profile)

        assert result[0]["_score"] == 8
        assert result[1]["_score"] == 3

    def test_fallback_quando_gemini_falha(self, sample_config, monkeypatch):
        profile = sample_config["perfil"]
        items = [{"title": "Notícia 1", "source_name": "g1"}]

        def boom(*args, **kwargs):
            raise RuntimeError("falha de rede")

        monkeypatch.setattr(content_enricher, "_gemini_call_with_retry", boom)

        result = profile_filter.score_batch_with_gemini(items, profile)

        assert result[0]["_score"] == 5
        assert result[0]["_motivo"] == "fallback"


class TestFilterAndScoreItems:
    def test_pipeline_filtra_bloqueados_e_ordena(self, sample_config, empty_adaptive_state, monkeypatch):
        profile = sample_config["perfil"]
        items = [
            {"title": "Notícia de tecnologia", "source_name": "g1", "text": "", "published_at": "2025-06-10"},
            {"title": "Seu horóscopo do dia", "source_name": "g1", "text": "", "published_at": "2025-06-10"},
        ]

        fake_response = json.dumps([{"i": 1, "score": 9, "motivo": "tecnologia"}])
        monkeypatch.setattr(content_enricher, "_gemini_call_with_retry", lambda *a, **k: fake_response)
        monkeypatch.setattr(adaptive_engine, "load_state", lambda: empty_adaptive_state)
        monkeypatch.setattr(adaptive_engine, "save_state", lambda s: None)

        result = profile_filter.filter_and_score_items(items, profile)

        assert all("_score" in i for i in result)
        assert all("horóscopo" not in i["title"].lower() for i in result)

    def test_estado_frio_nao_zera_itens_relevantes(
        self, sample_config, empty_adaptive_state, monkeypatch
    ):
        """
        Reproduz o estado de um sistema recém-colocado em produção: zero
        feedback, zero reputação de fontes, zero vetor de interesses do
        YouTube (DEFAULT_STATE). Itens bem avaliados pelo Gemini e
        publicados hoje devem passar pelo pipeline normalmente — sem isso,
        o briefing matinal fica vazio na primeira execução real.
        """
        from datetime import date

        profile = sample_config["perfil"]
        hoje = date.today().isoformat()
        items = [
            {
                "title": "Avanço importante em inteligência artificial",
                "source_name": "G1",
                "text": "",
                "published_at": hoje,
            },
            {
                "title": "Reflexão sobre fé e tradição católica",
                "source_name": "Vatican News",
                "text": "",
                "published_at": hoje,
            },
        ]

        fake_response = json.dumps(
            [
                {"i": 1, "score": 8, "motivo": "tecnologia"},
                {"i": 2, "score": 8, "motivo": "fé"},
            ]
        )
        monkeypatch.setattr(content_enricher, "_gemini_call_with_retry", lambda *a, **k: fake_response)
        monkeypatch.setattr(adaptive_engine, "load_state", lambda: empty_adaptive_state)
        monkeypatch.setattr(adaptive_engine, "save_state", lambda s: None)

        result = profile_filter.filter_and_score_items(items, profile)

        assert len(result) == 2
        assert all(i["_score"] >= profile["score_minimo_enviar"] for i in result)
