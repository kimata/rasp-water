#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Liveness のチェックを行います

Usage:
  healthz.py [-c CONFIG] [-d]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します．[default: config.yaml]
  -d                : デバッグモードで動作します．
"""

from docopt import docopt

import logging
import pathlib
import datetime
import sys


sys.path.append(str(pathlib.Path(__file__).parent.parent / "lib"))

import logger
from config import load_config


def check_liveness_impl(name, liveness_file, interval):
    if not liveness_file.exists():
        logging.warning("{name} is not executed.".format(name=name))
        return False

    elapsed = datetime.datetime.now() - datetime.datetime.fromtimestamp(
        liveness_file.stat().st_mtime
    )
    # NOTE: 少なくとも1分は様子を見る
    if elapsed.seconds > max(interval * 2, 60):
        logging.warning(
            "Execution interval of {name} is too long. ({elapsed:,} sec)".format(
                name=name, elapsed=elapsed.seconds
            )
        )
        return False

    return True


def check_liveness(target_list):
    for target in target_list:
        if not check_liveness_impl(
            target["name"], target["liveness_file"], target["interval"]
        ):
            return False

    return True


######################################################################
args = docopt(__doc__)

config_file = args["-c"]
debug_mode = args["-d"]

if debug_mode:
    log_level = logging.DEBUG
else:
    log_level = logging.INFO

logger.init(
    "hems.rasp-water",
    level=log_level,
)

logging.info("Using config config: {config_file}".format(config_file=config_file))
config = load_config(config_file)

target_list = []
for name in ["scheduler", "valve_control", "flow_notify"]:
    target_list.append(
        {
            "name": name,
            "liveness_file": pathlib.Path(config["liveness"]["file"][name]),
            "interval": 10,
        }
    )

if check_liveness(target_list):
    logging.info("OK.")
    sys.exit(0)
else:
    sys.exit(-1)
