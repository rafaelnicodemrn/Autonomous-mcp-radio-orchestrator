import src.telegram_sender as telegram_sender


class TestEscapeHtml:
    def test_escapa_caracteres_especiais(self):
        assert telegram_sender._escape_html("<b>A & B</b>") == "&lt;b&gt;A &amp; B&lt;/b&gt;"

    def test_string_vazia_ou_none(self):
        assert telegram_sender._escape_html("") == ""
        assert telegram_sender._escape_html(None) == ""


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
