from unittest.mock import AsyncMock, MagicMock

import pytest

import src.telegram_sender as telegram_sender


class TestEscapeHtml:
    def test_escapa_caracteres_especiais(self):
        assert telegram_sender._escape_html("<b>A & B</b>") == "&lt;b&gt;A &amp; B&lt;/b&gt;"

    def test_string_vazia_ou_none(self):
        assert telegram_sender._escape_html("") == ""
        assert telegram_sender._escape_html(None) == ""


class TestSourceTags:
    def test_biblia_nao_recebe_tag_tecnologia(self):
        """
        Regressão: 'ia' (de 'inteligência artificial') casava como
        substring dentro de 'biblia', atribuindo #tecnologia indevidamente.
        """
        tags = telegram_sender._source_tags("biblia", "Palavra do Dia")
        assert tags == "#catolicismo"
        assert "#tecnologia" not in tags

    def test_inteligencia_artificial_recebe_tag_tecnologia(self):
        tags = telegram_sender._source_tags("inteligencia-artificial", "IA")
        assert "#tecnologia" in tags

    def test_gremio_recebe_tag_futebol(self):
        tags = telegram_sender._source_tags("gremio", "Gaúcha")
        assert tags == "#futebol"

    def test_fonte_sem_match_retorna_vazio(self):
        assert telegram_sender._source_tags("efemerides", "Efemérides") == ""


class TestSendBriefingHeader:
    @pytest.mark.asyncio
    async def test_inclui_clima_cotacao_e_versiculo_sem_emoji_duplicado(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()

        await telegram_sender.send_briefing_header(
            bot,
            123,
            weather_text="🌤️ 24°C, parcialmente nublado em Medianeira",
            finance_text="💵 USD/BRL: R$ 5,42",
            verse="📖 \"texto\" — Ref 1:1",
        )

        sent_text = bot.send_message.call_args.kwargs["text"]
        assert sent_text.count("🌤️") == 1
        assert sent_text.count("💵") == 1
        assert "Medianeira" in sent_text
        assert "R$ 5,42" in sent_text

    @pytest.mark.asyncio
    async def test_omite_linhas_quando_strings_vazias(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()

        await telegram_sender.send_briefing_header(bot, 123)

        sent_text = bot.send_message.call_args.kwargs["text"]
        assert "Bom dia, Rafael" in sent_text


class TestFormatItemHtml:
    def test_inclui_titulo_e_link(self, sample_item):
        enriched = dict(sample_item, url="https://example.com/noticia", _score=8)
        html = telegram_sender.format_item_html(sample_item, enriched)

        assert "Grêmio vence clássico por 2 a 1" in html
        assert "https://example.com/noticia" in html
        assert "<b>" in html

    def test_escapa_titulo_com_html(self, sample_item):
        item = dict(sample_item, title="Notícia <script> & cia")
        enriched = dict(item, url="", _score=5)
        html = telegram_sender.format_item_html(item, enriched)

        assert "<script>" not in html
        assert "&lt;script&gt;" in html
