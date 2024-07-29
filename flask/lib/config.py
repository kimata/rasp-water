#!/usr/bin/env python3
import pathlib

import yaml

CONFIG_PATH = "config.yaml"


def load_config(config_path=CONFIG_PATH):
    with pathlib.Path(config_path).resolve().open(mode="r") as file:
        return yaml.load(file, Loader=yaml.SafeLoader)
