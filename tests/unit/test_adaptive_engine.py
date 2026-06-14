import src.adaptive_engine as adaptive_engine


class TestCalculateDynamicWeights:
    def test_default_weights_sem_dados(self, empty_adaptive_state):
        weights = adaptive_engine.calculate_dynamic_weights(empty_adaptive_state)
        assert abs(sum(weights.values()) - 1.0) < 0.01, "Pesos devem somar 1.0"
        assert all(v >= 0 for v in weights.values()), "Pesos devem ser não-negativos"

    def test_pesos_com_feedback_suficiente(self, empty_adaptive_state):
        state = empty_adaptive_state
        state["source_reputation"] = {
            f"fonte_{i}": {"total_score": 5, "count": 1, "avg": 5.0, "last_updated": "2025-06-10"}
            for i in range(3)
        }
        for i in range(5):
            state["feedback_history"].append({
                "item_hash": f"hash_{i}", "source_name": "test_src",
                "source_id": f"id_{i}", "gemini_score": 7,
                "feedback": "+1", "date": "2025-06-10T10:00:00"
            })
        weights = adaptive_engine.calculate_dynamic_weights(state)
        assert weights["feedback"] > 0, "Peso de feedback deve ser > 0 com dados suficientes"
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_pesos_com_youtube_suficiente(self, empty_adaptive_state):
        state = empty_adaptive_state
        state["source_reputation"] = {
            f"fonte_{i}": {"total_score": 5, "count": 1, "avg": 5.0, "last_updated": "2025-06-10"}
            for i in range(3)
        }
        state["youtube_interest_vector"] = {"tecnologia": 0.8, "futebol": 0.6, "fé": 0.4}
        weights = adaptive_engine.calculate_dynamic_weights(state)
        assert weights["youtube"] > 0
        assert abs(sum(weights.values()) - 1.0) < 0.01


class TestComputeAdaptiveScore:
    def test_score_dentro_do_range(self, empty_adaptive_state, sample_item):
        score = adaptive_engine.compute_adaptive_score(sample_item, gemini_score=7.5, state=empty_adaptive_state)
        assert 0.0 <= score <= 10.0, f"Score {score} fora do range esperado [0, 10]"

    def test_score_item_sem_data(self, empty_adaptive_state):
        item = {"title": "Sem data", "source_name": "test", "source_id": "x", "_score": 5.0}
        score = adaptive_engine.compute_adaptive_score(item, gemini_score=5.0, state=empty_adaptive_state)
        assert isinstance(score, float)
        assert 0.0 <= score <= 10.0


class TestRecordFeedback:
    def test_feedback_positivo_salvo(self, empty_adaptive_state, monkeypatch):
        saved = {}
        monkeypatch.setattr(adaptive_engine, "load_state", lambda: empty_adaptive_state)
        monkeypatch.setattr(adaptive_engine, "save_state", lambda state: saved.setdefault("state", state))

        adaptive_engine.record_feedback("hash_001", "gaucha_rss", "id_001", 7, "+1")

        assert "state" in saved
        assert len(saved["state"]["feedback_history"]) == 1
        assert saved["state"]["feedback_history"][0]["feedback"] == "+1"

    def test_feedback_history_max_500(self, empty_adaptive_state, monkeypatch):
        state = empty_adaptive_state
        state["feedback_history"] = [
            {"item_hash": f"h{i}", "source_name": "s", "source_id": f"i{i}",
             "gemini_score": 5, "feedback": "+1", "date": "2025-01-01T00:00:00"}
            for i in range(500)
        ]
        saved = {}
        monkeypatch.setattr(adaptive_engine, "load_state", lambda: state)
        monkeypatch.setattr(adaptive_engine, "save_state", lambda s: saved.setdefault("state", s))

        adaptive_engine.record_feedback("new_hash", "src", "id_new", 8, "+1")

        assert len(saved["state"]["feedback_history"]) == 500, "Deve manter máximo de 500"
        assert saved["state"]["feedback_history"][-1]["item_hash"] == "new_hash"
