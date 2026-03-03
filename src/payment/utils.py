import logging
import os

import yaml

from payment.models import Config


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def load_config(config_path: str) -> Config:
    """Load and parse a YAML config file.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Parsed Config object.
    """
    with open(config_path) as f:
        return Config(**yaml.safe_load(f))
