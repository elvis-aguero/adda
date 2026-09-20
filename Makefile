.DEFAULT_GOAL := help

PACKAGEDIR := dist
COVERAGEREPORTDIR := coverage_html_report

.PHONY: help test test-html build docs lint promptmap promptmap-status attest-paper decline-paper

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  test        Run the tests with pytest"
	@echo "  test-html   Run the tests and open the HTML coverage report"
	@echo "  build       Build the package"
	@echo "  docs        Build the documentation with mkdocs"
	@echo "  lint        Lint the code with ruff"
	@echo "  promptmap   Regenerate internal/promptmap.html (prompt + gate provenance)"
	@echo "  promptmap-status  Is the map in sync with the code, and with what is published?"
	@echo "  attest-paper   Sign that paper/ reflects the code as of HEAD"
	@echo "  decline-paper  WHY='...' Sign, recording that no decision was taken"

test:
	uv run pytest -m "not integration and not ollama and not corpus"

test-html:
	pytest
	xdg-open ./$(COVERAGEREPORTDIR)/index.html

build:
	uv build

docs:
	mkdocs build

lint:
	ruff check

promptmap:
	uv run python internal/tools/promptmap.py

promptmap-status:
	uv run python internal/tools/promptmap_sync.py

attest-paper:
	uv run python internal/tools/paper_attestation.py --attest

decline-paper:
	@test -n "$(WHY)" || (echo "usage: make decline-paper WHY='no design decision here'"; exit 1)
	uv run python internal/tools/paper_attestation.py --decline "$(WHY)"
