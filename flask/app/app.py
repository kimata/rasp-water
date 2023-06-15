#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水やりを自動化するアプリのサーバーです

Usage:
  app.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します．[default: config.yaml]
  -D                : ダミーモードで実行します．CI テストで利用することを想定しています．
"""

from docopt import docopt

from flask import Flask
import sys
import pathlib
import time
import logging
import atexit

sys.path.append(str(pathlib.Path(__file__).parent.parent / "lib"))

import rasp_water_valve
import rasp_water_schedule

import webapp_base
import webapp_util
import webapp_log
import webapp_event

import valve


def notify_terminate():
    valve.set_state(valve.VALVE_STATE.CLOSE)
    webapp_log.app_log("🏃 アプリを再起動します．")
    # NOTE: ログを送信できるまでの時間待つ
    time.sleep(1)


atexit.register(notify_terminate)


if __name__ == "__main__":
    import logger
    import os
    from config import load_config

    args = docopt(__doc__)

    config_file = args["-c"]
    dummy_mode = os.environ.get("DUMMY_MODE", args["-D"])

    logger.init("hems.rasp-water", level=logging.INFO)

    if dummy_mode:
        logging.warning("Set dummy mode")
        os.environ["DUMMY_MODE"] = "true"

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app = Flask(__name__)

    app.config["CONFIG"] = load_config(config_file)
    app.config["DUMMY_MODE"] = dummy_mode

    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

    app.register_blueprint(rasp_water_valve.blueprint)
    app.register_blueprint(rasp_water_schedule.blueprint)

    app.register_blueprint(webapp_base.blueprint)
    app.register_blueprint(webapp_event.blueprint)
    app.register_blueprint(webapp_log.blueprint)
    app.register_blueprint(webapp_util.blueprint)

    # app.debug = True
    # NOTE: スクリプトの自動リロード停止したい場合は use_reloader=False にする
    app.run(host="0.0.0.0", threaded=True, use_reloader=True)
