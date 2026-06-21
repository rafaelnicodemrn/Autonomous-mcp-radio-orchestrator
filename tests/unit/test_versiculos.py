from datetime import date

import src.data.versiculos as versiculos


class TestGetVerseOfDay:
    def test_retorna_dict_com_texto_e_referencia(self):
        verse = versiculos.get_verse_of_day()
        assert "texto" in verse
        assert "referencia" in verse

    def test_e_deterministico_no_mesmo_dia(self):
        a = versiculos.get_verse_of_day()
        b = versiculos.get_verse_of_day()
        assert a == b

    def test_indice_nunca_sai_dos_limites(self, monkeypatch):
        class _FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 12, 31)

        monkeypatch.setattr(versiculos, "date", _FakeDate)
        verse = versiculos.get_verse_of_day()
        assert verse in versiculos.VERSICULOS

    def test_todos_os_dias_do_ano_retornam_versiculo_valido(self, monkeypatch):
        for yday in range(1, 367):

            class _FakeDate(date):
                @classmethod
                def today(cls):
                    return date.fromordinal(date(2026, 1, 1).toordinal() + yday - 1)

            monkeypatch.setattr(versiculos, "date", _FakeDate)
            verse = versiculos.get_verse_of_day()
            assert verse in versiculos.VERSICULOS


class TestFormatVerseOfDay:
    def test_formato_esperado(self):
        result = versiculos.format_verse_of_day()
        assert result.startswith("📖")
        assert "—" in result
