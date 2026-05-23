"""Load the YAML config and compute a stable hash of it.

The config hash is stored on every ingest/run/report so a result can always be
tied back to the exact knobs that produced it.
"""

import os

import yaml

from .hashing import content_hash

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "default.yaml"
)


def load_config(path: str | None = None) -> dict:
    with open(path or DEFAULT_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def config_hash(config: dict) -> str:
    """SHA-256 over the canonical (sorted) JSON form of the config."""
    return content_hash(config)
