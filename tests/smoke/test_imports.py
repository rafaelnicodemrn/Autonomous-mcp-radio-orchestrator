import os

import yaml


def test_import_adaptive_engine():
    import src.adaptive_engine


def test_import_profile_filter():
    import src.profile_filter


def test_import_content_enricher():
    import src.content_enricher


def test_import_telegram_sender():
    import src.telegram_sender


def test_import_telegram_bot():
    import telegram_bot


def test_import_main():
    import main


def test_import_scheduler():
    import scheduler


def test_config_yaml_example_parses():
    config_path = os.getenv("CONFIG_PATH", "config.yaml.example")
    assert os.path.exists(config_path), f"{config_path} não encontrado"
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    for key in ("radio", "llm", "tts", "sources", "schedule", "telegram"):
        assert key in data
