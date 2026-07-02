.PHONY: install playground test run generate-traces grade

install:
	uv sync

playground:
	uv run adk web . --host 127.0.0.1 --port 8080 --allow_origins '*' --reload_agents --trigger_sources=pubsub

run:
	uv run python -m pr_triage_agent.fast_api_app

test:
	uv run pytest

generate-traces:
	uv run python tests/eval/generate_traces.py

grade:
	uv run agents-cli eval grade --traces artifacts/traces/generated_traces.json --config tests/eval/eval_config.yaml
