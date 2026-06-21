import time
from datetime import datetime, timedelta, timezone

import src.sources.rss as rss


class _FakeEntry(dict):
    """feedparser entries se comportam como dict com .get()."""


def _entry(title, url, summary="", published_parsed=None):
    e = _FakeEntry(title=title, link=url, summary=summary)
    if published_parsed is not None:
        e["published_parsed"] = published_parsed
    return e


def _struct_time_days_ago(days: int):
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return time.struct_time(dt.timetuple())


class _FakeFeed:
    def __init__(self, entries, title="Feed Teste"):
        self.entries = entries
        self.feed = {"title": title}


class TestRecencyFilter:
    def test_descarta_item_mais_velho_que_lookback(self, monkeypatch):
        old_entry = _entry("Notícia antiga", "https://x.com/1", published_parsed=_struct_time_days_ago(10))
        monkeypatch.setattr(rss, "feedparser", _FakeModule(_FakeFeed([old_entry])))
        monkeypatch.setattr(rss, "_extract_text", lambda url: "")

        source_config = {"feeds": [{"url": "https://feed", "name": "Feed"}], "settings": {"days_lookback": 1}}
        items = rss.fetch(source_config)

        assert items == []

    def test_mantem_item_dentro_do_lookback(self, monkeypatch):
        fresh_entry = _entry("Notícia recente", "https://x.com/2", published_parsed=_struct_time_days_ago(0))
        monkeypatch.setattr(rss, "feedparser", _FakeModule(_FakeFeed([fresh_entry])))
        monkeypatch.setattr(rss, "_extract_text", lambda url: "")

        source_config = {"feeds": [{"url": "https://feed", "name": "Feed"}], "settings": {"days_lookback": 1}}
        items = rss.fetch(source_config)

        assert len(items) == 1
        assert items[0]["url"] == "https://x.com/2"

    def test_sem_data_parseavel_nao_finge_ser_recente(self, monkeypatch):
        """
        Entrada sem published_parsed/updated_parsed deve passar pelo filtro
        de cutoff (não há como saber se é antiga), mas published_at deve
        ficar vazio em vez de "agora" — senão o item ganha bônus de
        recência máximo indevidamente e pode escapar de outros filtros.
        """
        undated_entry = _entry("Sem data", "https://x.com/3")
        monkeypatch.setattr(rss, "feedparser", _FakeModule(_FakeFeed([undated_entry])))
        monkeypatch.setattr(rss, "_extract_text", lambda url: "")

        source_config = {"feeds": [{"url": "https://feed", "name": "Feed"}], "settings": {"days_lookback": 1}}
        items = rss.fetch(source_config)

        assert len(items) == 1
        assert items[0]["published_at"] == ""


class _FakeModule:
    """Substitui o módulo feedparser só no que rss.py usa: parse()."""

    def __init__(self, feed):
        self._feed = feed

    def parse(self, url):
        return self._feed
