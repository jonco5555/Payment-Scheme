import yaml

from payment.models import Config


def load_config(config_path: str) -> Config:
    """Load and parse a YAML config file.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Parsed Config object.
    """
    with open(config_path) as f:
        return Config(**yaml.safe_load(f))
