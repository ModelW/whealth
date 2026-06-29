UV := uv
PNPX := pnpx
ALL_PYTHON := packages
MD_FILES := $(shell find . -name '*.md' -not -path './.venv/*' -not -path './node_modules/*' 2>/dev/null)
WHOSPITAL := packages/whospital

.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  format     Auto-format Python code (ruff) and markdown (prettier)"
	@echo "  lint       Check code quality with ruff and prettier"
	@echo "  test       Run pytest suite"
	@echo "  typecheck  Run mypy static type checking"
	@echo "  clean      Run format, lint, and typecheck in sequence"
	@echo "  serve      Start prod-like ASGI server via granian"
	@echo ""
	@echo "Depends: uv, pnpx (for prettier)"

.PHONY: format
format:
	$(UV) run ruff format $(ALL_PYTHON)
	-$(UV) run ruff check --fix $(ALL_PYTHON) 2>&1
ifneq ($(MD_FILES),)
	-$(PNPX) prettier --write --prose-wrap always $(MD_FILES) 2>&1
endif

.PHONY: lint
lint:
	$(UV) run ruff check $(ALL_PYTHON)
ifneq ($(MD_FILES),)
	$(PNPX) prettier --check --prose-wrap always $(MD_FILES)
endif

.PHONY: test
test:
	$(UV) run -m pytest packages/whospital/tests/ -v

.PHONY: typecheck
typecheck:
	$(UV) run mypy $(ALL_PYTHON)

.PHONY: clean
clean: format lint typecheck

.PHONY: serve
serve:
	DJANGO_DEBUG=False $(UV) run python $(WHOSPITAL)/src/whospital/manage.py collectstatic --noinput --clear 2>&1 | tail -3
	DJANGO_DEBUG=False $(UV) run granian --interface asgi --host 0.0.0.0 --port 8000 whospital.asgi:application
