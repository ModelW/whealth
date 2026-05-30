UV := uv
PNPX := pnpx
ALL_PYTHON := packages
MD_FILES := $(shell find . -name '*.md' -not -path './.venv/*' -not -path './node_modules/*' 2>/dev/null)

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
