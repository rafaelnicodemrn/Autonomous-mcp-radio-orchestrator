import json

import src.profile_filter as profile_filter
import content_enricher
import adaptive_engine


class TestPipelineCompleto:
    def test_fluxo_filter_and_score_aplica_diversidade(self, sample_config, sample_items, empty_adaptive_state, monkeypatch):
        profile = sample_config["perfil"]

        scores = json.dumps([{"i": i + 1, "score": 7, "motivo": "ok"} for i in range(len(sample_items[:5]))])
        monkeypatch.setattr(content_enricher, "_gemini_call_with_retry", lambda *a, **k: scores)
        monkeypatch.setattr(adaptive_engine, "load_state", lambda: empty_adaptive_state)
        monkeypatch.setattr(adaptive_engine, "save_state", lambda s: None)

        result = profile_filter.filter_and_score_items(sample_items, profile)

        assert isinstance(result, list)
        assert all("_score" in item for item in result)
        assert all(0 <= item["_score"] <= 10 for item in result)
