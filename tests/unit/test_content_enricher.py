import src.content_enricher as content_enricher


class TestDiversityGuard:
    def test_max_2_por_topico(self):
        items = [
            {"title": "Grêmio vence jogo 1", "source_name": "gaucha"},
            {"title": "Grêmio marca gol 2", "source_name": "gaucha"},
            {"title": "Grêmio terceira notícia", "source_name": "gaucha"},
        ]
        result = content_enricher.diversity_guard(items)
        gremio_items = [i for i in result if "grêmio" in i["title"].lower()]
        assert len(gremio_items) <= 2, "Máximo 2 itens por tópico"

    def test_itens_diferentes_passam(self):
        items = [
            {"title": "Tecnologia avança em 2025", "source_name": "techcrunch"},
            {"title": "Papa Francisco visita Brasil", "source_name": "vatican"},
            {"title": "Grêmio vence clássico", "source_name": "gaucha"},
        ]
        result = content_enricher.diversity_guard(items)
        assert len(result) == 3, "Itens de tópicos distintos devem passar todos"

    def test_lista_vazia(self):
        assert content_enricher.diversity_guard([]) == []


class TestScoreItem:
    def test_score_entre_0_e_10(self, sample_item):
        score = content_enricher.score_item(sample_item)
        assert 0 <= score <= 10


class TestDeduplicate:
    def test_remove_url_duplicada_mantendo_maior_score(self):
        items = [
            {"title": "Notícia A", "url": "https://x.com/a", "_score": 5},
            {"title": "Notícia A repetida", "url": "https://x.com/a", "_score": 8},
        ]
        result = content_enricher.deduplicate(items)
        assert len(result) == 1
        assert result[0]["_score"] == 8

    def test_remove_titulo_similar(self):
        items = [
            {"title": "Grêmio vence clássico no Beira-Rio", "_score": 5},
            {"title": "Grêmio vence o clássico no Beira-Rio", "_score": 9},
        ]
        result = content_enricher.deduplicate(items)
        assert len(result) == 1
        assert result[0]["_score"] == 9
