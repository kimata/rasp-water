#!/usr/bin/env python3
import logging
import pathlib

import yaml

CONFIG_PATH = "config.yaml"


def load_config(config_path=CONFIG_PATH):
    config_path = pathlib.Path(config_path).resolve()
    logging.info("Load config: %s", config_path)
    with config_path.open(mode="r") as file:
        return yaml.load(file, Loader=yaml.SafeLoader)


if __name__ == "__main__":
    import logger

    logger.init("test", level=logging.INFO)

    load_config()
