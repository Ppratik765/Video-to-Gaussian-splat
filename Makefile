.PHONY: help test lint typecheck format clean

help:
	@echo "Makefile has been deprecated in favor of tasks.py for cross-platform compatibility."
	@echo "Please run: python tasks.py <cmd>"
	@echo "Available commands via tasks.py:"
	@echo "  test       - Run pytest"
	@echo "  lint       - Run ruff check"
	@echo "  typecheck  - Run mypy"
	@echo "  format     - Run ruff format"

test:
	python tasks.py test

lint:
	python tasks.py lint

typecheck:
	python tasks.py typecheck

format:
	python tasks.py format
