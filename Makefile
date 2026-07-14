# StreamingViewerTV — builder vs viewer
#
#   make               # info (default)
#   make build         # download/enrich/epg → viewer.db (no probe)
#   make probe         # HLS probe → streams_probed.csv
#   make build-probed  # full pipeline including probe (slow)
#   make run           # start the FastAPI UI
#   make clean         # remove generated data under iptv_export/
#   make test          # run all tests including Playwright UI (must pass)

.PHONY: info build build-probed probe run sync clean test help

UV ?= uv
EXPORT := iptv_export
DB := $(EXPORT)/viewer.db

# Probe knobs (override on the command line):
#   make probe LIMIT=50
#   make probe WORKERS=8
#   make build-probed LIMIT=100
WORKERS ?= 500
LIMIT ?=
PROBE_DEEP ?= 1

.DEFAULT_GOAL := info

info help:
	@echo "StreamingViewerTV"
	@echo ""
	@echo "Targets:"
	@echo "  make info          Show this help (default)"
	@echo "  make build         Build catalog DB without probing"
	@echo "  make probe         Probe stream health → streams_probed.csv"
	@echo "  make build-probed  Build DB including probe (slow for full catalog)"
	@echo "  make run           Start viewer UI"
	@echo "  make sync          Install/update deps (uv sync)"
	@echo "  make clean         Remove generated data under $(EXPORT)/"
	@echo "  make test          Run all tests including Playwright UI (must pass)"
	@echo ""
	@echo "Probe options:"
	@echo "  make probe LIMIT=50          # quick sample"
	@echo "  make probe                   # all streams (default)"
	@echo "  make build-probed LIMIT=100  # build + limited probe"
	@echo "  WORKERS=$(WORKERS)  PROBE_DEEP=$(PROBE_DEEP) (0 disables --deep)"
	@echo ""
	@echo "Layout:"
	@echo "  builder/        offline pipeline → $(DB)"
	@echo "  stream_viewer/  FastAPI UI (reads $(DB))"
	@echo ""
	@echo "Data status:"
	@if [ -f "$(DB)" ]; then \
		echo "  [ok] $(DB) ($$(du -h "$(DB)" | cut -f1))"; \
		$(UV) run python -c "from pathlib import Path; from stream_viewer.db import connect, db_status; \
c=connect(Path('$(DB)')); s=db_status(c); c.close(); \
print(f\"       streams={s['streams']} programmes={s['programmes']} source={s['streams_source'] or '?'}\")"; \
	else \
		echo "  [missing] $(DB) — run: make build  or  make build-probed"; \
	fi
	@if [ -f "$(EXPORT)/streams_probed.csv" ]; then \
		echo "  [ok] $(EXPORT)/streams_probed.csv ($$(du -h "$(EXPORT)/streams_probed.csv" | cut -f1))"; \
	else \
		echo "  [missing] streams_probed.csv — run: make probe"; \
	fi

sync:
	$(UV) sync --group dev

build: sync
	$(UV) run stream-viewer-build

# HLS health grades. Default = full catalog; pass LIMIT=N for a sample.
probe: sync
	@if [ ! -f "$(EXPORT)/streams_enriched.csv" ] && [ ! -f "$(EXPORT)/streams.csv" ]; then \
		echo "No streams CSV found. Run: make build first (or make build-probed)."; \
		exit 1; \
	fi
	@deep_flag=""; \
	if [ "$(PROBE_DEEP)" != "0" ]; then deep_flag="--deep"; fi; \
	if [ -n "$(LIMIT)" ]; then \
		echo "Probing first $(LIMIT) stream(s)…"; \
		$(UV) run python -m builder.probe --limit $(LIMIT) --workers $(WORKERS) $$deep_flag; \
	else \
		echo "Probing ALL streams (slow)…"; \
		$(UV) run python -m builder.probe --all --workers $(WORKERS) $$deep_flag; \
	fi
	@echo "Done. Import into DB with: make build   # or make build-probed"

# Full rebuild including probe, then import streams_probed.csv into viewer.db.
build-probed: sync
	@deep_flag=""; \
	if [ "$(PROBE_DEEP)" != "0" ]; then deep_flag="--probe-deep"; fi; \
	if [ -n "$(LIMIT)" ]; then \
		$(UV) run stream-viewer-build --probe --probe-limit $(LIMIT) --probe-workers $(WORKERS) $$deep_flag; \
	else \
		$(UV) run stream-viewer-build --probe --probe-all --probe-workers $(WORKERS) $$deep_flag; \
	fi

run: sync
	@if [ ! -f "$(DB)" ]; then \
		echo "Missing $(DB). Run: make build  or  make build-probed"; \
		exit 1; \
	fi
	$(UV) run stream-viewer

clean:
	@echo "Removing generated files under $(EXPORT)/ …"
	@rm -f $(DB) $(DB)-*
	@rm -f $(EXPORT)/*.csv
	@rm -f $(EXPORT)/epg/* $(EXPORT)/epg_cache/* $(EXPORT)/epg_channels/*
	@mkdir -p $(EXPORT)/epg $(EXPORT)/epg_cache $(EXPORT)/epg_channels
	@touch $(EXPORT)/.gitkeep $(EXPORT)/epg/.gitkeep $(EXPORT)/epg_channels/.gitkeep
	@echo "Done. Run: make build-probed   # or make build && make probe && make build"

test: sync
	$(UV) run playwright install chromium
	$(UV) run pytest -q --tb=short
	@echo "All tests passed."
