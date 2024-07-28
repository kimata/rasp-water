#!/usr/bin/env python3
import pathlib

import yaml

CONFIG_PATH = "config.yaml"


def abs_path(config_path=CONFIG_PATH):
    return pathlib.Path(pathlib.Path.cwd(), config_path)


# NOTE: プロジェクトによって，大文字と小文字が異なるのでここで吸収する
def get_db_config(config):
    if "INFLUXDB" in config:
        return {
            "token": config["INFLUXDB"]["TOKEN"],
            "bucket": config["INFLUXDB"]["BUCKET"],
            "url": config["INFLUXDB"]["URL"],
            "org": config["INFLUXDB"]["ORG"],
        }
    else:
        return {
            "token": config["influxdb"]["token"],
            "bucket": config["influxdb"]["bucket"],
            "url": config["influxdb"]["url"],
            "org": config["influxdb"]["org"],
        }


def load_config(config_path=CONFIG_PATH):
    with abs_path(config_path).open(mode="r") as file:
        return yaml.load(file, Loader=yaml.SafeLoader)
