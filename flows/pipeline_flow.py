"""Prefect orchestration of the Corridor Watch pipeline.

Why orchestration for a monitoring product: customer deliveries recur (new
imagery every few days, dozens of corridors), so runs need retries, state,
and observability — not a cron job and hope. Each stage is a Prefect task
with retry semantics tuned to its failure mode: network fetches retry,
deterministic analysis does not (a deterministic failure will just fail
again — it needs a human, not a retry).

Prefect is an optional dependency; without it this module still imports and
runs sequentially (no-op decorators), so the core pipeline never depends on
the orchestrator being installed.
"""
from __future__ import annotations

try:
    from prefect import flow, task

    PREFECT = True
except ImportError:  # graceful degradation: run as plain functions
    PREFECT = False

    def task(*args, **kwargs):
        def wrap(fn):
            return fn
        return wrap if not args or not callable(args[0]) else args[0]

    def flow(*args, **kwargs):
        def wrap(fn):
            return fn
        return wrap if not args or not callable(args[0]) else args[0]


from corridor_watch.config import load_config
from corridor_watch import cli


@task(retries=3, retry_delay_seconds=60)
def fetch_inputs(config_path: str) -> None:
    """Network stage — transient failures (STAC/Overpass timeouts) retry."""
    cli.cmd_fetch(load_config(config_path))


@task(retries=0)
def generate_demo_inputs(config_path: str) -> None:
    cli.cmd_demo(load_config(config_path))


@task(retries=0)
def analyze_and_deliver(config_path: str) -> int:
    """Deterministic stage — no retries; failures require investigation."""
    return cli.cmd_run(load_config(config_path))


@flow(name="corridor-watch-delivery", log_prints=True)
def delivery_flow(config_path: str = "config/corridor_brandenburg.yaml", demo: bool = False):
    if demo:
        generate_demo_inputs(config_path)
    else:
        fetch_inputs(config_path)
    return analyze_and_deliver(config_path)


if __name__ == "__main__":
    delivery_flow(demo=True)
