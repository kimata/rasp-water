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

import my_lib.healthz


def check_liveness(target_list, port):
    for target in target_list:
        if not my_lib.healthz.check_liveness(target["name"], target["liveness_file"], target["interval"]):
            return False

    return my_lib.healthz.check_port(port)


######################################################################
if __name__ == "__main__":
    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    port = args["-p"]
    debug_mode = args["-d"]

    my_lib.logger.init("hems.rasp-water", level=logging.DEBUG if debug_mode else logging.INFO)

    logging.info("Using config config: %s", config_file)
    config = my_lib.config.load(config_file)

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
