.PHONY: lint
lint:
	@tox

build:
	@charm build -rl DEBUG
