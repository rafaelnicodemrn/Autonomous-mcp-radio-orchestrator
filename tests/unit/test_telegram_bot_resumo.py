from unittest.mock import AsyncMock, MagicMock

import pytest

import telegram_bot


def _make_update():
    update = MagicMock()
    update.effective_chat.id = 123
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture(autouse=True)
def no_command_usage(monkeypatch):
    monkeypatch.setattr(telegram_bot, "record_command_usage", lambda *a, **k: None)
    monkeypatch.setattr(telegram_bot, "load_profile", lambda: {"interesses_primarios": ["tecnologia"]})


class TestCmdResumo:
    @pytest.mark.asyncio
    async def test_usa_itens_ja_coletados_hoje(self, monkeypatch):
        update = _make_update()
        context = MagicMock()

        monkeypatch.setattr(
            telegram_bot,
            "_collect_from_episode_json",
            lambda sources: [{"title": "Notícia 1", "source_name": "G1"}],
        )
        monkeypatch.setattr(
            telegram_bot, "_gemini_call_with_retry", lambda *a, **k: "Resumo gerado pelo Gemini."
        )
        run_main_called = MagicMock()
        monkeypatch.setattr(telegram_bot, "_run_main_py", run_main_called)

        await telegram_bot.cmd_resumo(update, context)

        run_main_called.assert_not_called()
        sent_text = update.message.reply_text.call_args[0][0]
        assert "Resumo do dia" in sent_text
        assert "Resumo gerado pelo Gemini." in sent_text

    @pytest.mark.asyncio
    async def test_roda_coleta_rapida_quando_sem_itens_hoje(self, monkeypatch):
        update = _make_update()
        context = MagicMock()

        calls = {"n": 0}

        def fake_collect(sources):
            calls["n"] += 1
            return [] if calls["n"] == 1 else [{"title": "Notícia nova", "source_name": "G1"}]

        monkeypatch.setattr(telegram_bot, "_collect_from_episode_json", fake_collect)
        monkeypatch.setattr(telegram_bot, "_run_main_py", lambda sources: "fake_proc")

        async def fake_wait_and_collect(proc, sources, timeout=300):
            return [{"title": "Notícia nova", "source_name": "G1"}]

        monkeypatch.setattr(telegram_bot, "_wait_and_collect", fake_wait_and_collect)
        monkeypatch.setattr(telegram_bot, "_gemini_call_with_retry", lambda *a, **k: "Resumo.")

        await telegram_bot.cmd_resumo(update, context)

        assert update.message.reply_text.await_count == 2
        final_text = update.message.reply_text.call_args[0][0]
        assert "Resumo do dia" in final_text

    @pytest.mark.asyncio
    async def test_sem_conteudo_nenhum_avisa_usuario(self, monkeypatch):
        update = _make_update()
        context = MagicMock()

        monkeypatch.setattr(telegram_bot, "_collect_from_episode_json", lambda sources: [])
        monkeypatch.setattr(telegram_bot, "_run_main_py", lambda sources: "fake_proc")

        async def fake_wait_and_collect(proc, sources, timeout=300):
            return []

        monkeypatch.setattr(telegram_bot, "_wait_and_collect", fake_wait_and_collect)

        await telegram_bot.cmd_resumo(update, context)

        final_text = update.message.reply_text.call_args[0][0]
        assert "Nenhum conteúdo disponível" in final_text

    @pytest.mark.asyncio
    async def test_erro_no_gemini_nao_quebra_o_comando(self, monkeypatch):
        update = _make_update()
        context = MagicMock()

        monkeypatch.setattr(
            telegram_bot,
            "_collect_from_episode_json",
            lambda sources: [{"title": "Notícia 1", "source_name": "G1"}],
        )

        def boom(*a, **k):
            raise RuntimeError("falha no Gemini")

        monkeypatch.setattr(telegram_bot, "_gemini_call_with_retry", boom)

        await telegram_bot.cmd_resumo(update, context)

        final_text = update.message.reply_text.call_args[0][0]
        assert "Resumo do dia" in final_text
        assert "não foi possível gerar" in final_text.lower()
