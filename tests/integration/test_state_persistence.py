import os

import src.adaptive_engine as adaptive_engine


class TestStatePersistence:
    def test_load_state_cria_default_se_nao_existe(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / "adaptive_state.json")
        monkeypatch.setattr(adaptive_engine, "STATE_FILE", state_file)

        state = adaptive_engine.load_state()

        assert os.path.exists(state_file)
        assert state["signal_weights"] == adaptive_engine.DEFAULT_STATE["signal_weights"]

    def test_save_e_load_preserva_dados(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / "adaptive_state.json")
        monkeypatch.setattr(adaptive_engine, "STATE_FILE", state_file)

        state = adaptive_engine.load_state()
        state["total_feedback_given"] = 42
        adaptive_engine.save_state(state)

        reloaded = adaptive_engine.load_state()
        assert reloaded["total_feedback_given"] == 42

    def test_load_state_completa_campos_faltantes(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / "adaptive_state.json")
        monkeypatch.setattr(adaptive_engine, "STATE_FILE", state_file)

        adaptive_engine.save_state({"feedback_history": []})

        state = adaptive_engine.load_state()
        for key in adaptive_engine.DEFAULT_STATE:
            assert key in state
