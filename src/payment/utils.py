import yaml

from payment.models import Config


def load_config(config_path: str) -> Config:
    with open(config_path) as f:
        return Config(**yaml.safe_load(f))
