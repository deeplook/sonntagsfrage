UV ?= uv

.PHONY: help install build test

help:
	@printf '%s\n' \
	  'install  Sync runtime and development dependencies' \
	  'build    Build source and wheel distributions' \
	  'test     Install development dependencies and run Pytest'

install:
	$(UV) sync --all-groups

build:
	$(UV) build

test: install
	$(UV) run pytest
