.PHONY: install test smoke unit integration coverage lint format security clean

PY := .venv/Scripts/python

install:
	python -m venv .venv
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	$(PY) -m pytest tests/ -v

smoke:
	$(PY) -m pytest tests/smoke/ -v

unit:
	$(PY) -m pytest tests/unit/ -v

integration:
	$(PY) -m pytest tests/integration/ -v

coverage:
	$(PY) -m pytest tests/ --cov=src --cov=telegram_bot --cov-report=html
	@echo "Abra htmlcov/index.html para o relatorio completo"

lint:
	$(PY) -m flake8 src/ telegram_bot.py --max-line-length=100 --extend-ignore=E203,W503
	$(PY) -m black --check src/ telegram_bot.py
	$(PY) -m isort --check-only src/ telegram_bot.py

format:
	$(PY) -m black src/ telegram_bot.py
	$(PY) -m isort src/ telegram_bot.py

security:
	$(PY) -m bandit -r src/ telegram_bot.py -ll
	$(PY) -m pip_audit -r requirements.txt

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov coverage.xml .coverage
