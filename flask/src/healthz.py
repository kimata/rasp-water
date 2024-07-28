#!/usr/bin/env python3
"""
Liveness のチェックを行います

Usage:
  healthz.py [-c CONFIG] [-p PORT] [-d]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します．[default: config.yaml]
  -p PORT           : WEB サーバのポートを指定します．[default: 5000]
  -d                : デバッグモードで動作します．
"""

import logging
import pathlib
import sys
import time

import requests
from docopt import docopt

sys.path.append(str(pathlib.Path(__file__).parent.parent / "lib"))

import logger
from config import load_config


def check_liveness_impl(name, liveness_file, interval):
    if not liveness_file.exists():
        logging.warning("%s is not executed.", name)
        return False

    elapsed = time.time() - liveness_file.stat().st_mtime
    # NOTE: 少なくとも1分は様子を見る
    if elapsed > max(interval * 2, 60):
        logging.warning("Execution interval of %s is too long. %s sec)", name, f"{elapsed:,.1f}")
        return False

    return True


def check_port(port):
    try:
        if (
            requests.get(
                "http://{address}:{port}/".format(address="127.0.0.1", port=port), timeout=5
            ).status_code
            == 200
        ):
            return True
    except Exception:
        logging.exception("Failed to access Flask web server")

    return False


def check_liveness(target_list, port):
    for target in target_list:
        if not check_liveness_impl(target["name"], target["liveness_file"], target["interval"]):
            return False

    return check_port(port)


######################################################################
args = docopt(__doc__)

config_file = args["-c"]
port = args["-p"]
debug_mode = args["-d"]

log_level = logging.DEBUG if debug_mode else logging.INFO

logger.init(
    "hems.rasp-water",
    level=log_level,
)

logging.info("Using config config: %s", config_file)
config = load_config(config_file)

target_list = [
    {
        "name": name,
        "liveness_file": pathlib.Path(config["liveness"]["file"][name]),
        "interval": 10,
    }
    for name in ["scheduler", "valve_control", "flow_notify"]
]

if check_liveness(target_list, port):
    logging.info("OK.")
    sys.exit(0)
else:
    sys.exit(-1)
