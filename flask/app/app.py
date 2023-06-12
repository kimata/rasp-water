#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask
import sys
import pathlib
import time
import logging
import atexit

sys.path.append(str(pathlib.Path(__file__).parent.parent / "lib"))


import rasp_water_config
import rasp_water
import rasp_water_valve
import rasp_water_schedule
import rasp_water_util
import rasp_water_log
import rasp_water_event

import valve

app = Flask(__name__)

app.register_blueprint(rasp_water.blueprint)
app.register_blueprint(rasp_water_valve.blueprint)
app.register_blueprint(rasp_water_schedule.blueprint)
app.register_blueprint(rasp_water_event.blueprint)
app.register_blueprint(rasp_water_log.blueprint)
app.register_blueprint(rasp_water_util.blueprint)

app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True


def notify_terminate():
    valve.set_state(valve.VALVE_STATE.CLOSE)
    rasp_water_log.app_log("🏃 アプリを再起動します．")
    # NOTE: ログを送信できるまでの時間待つ
    time.sleep(1)


atexit.register(notify_terminate)


if __name__ == "__main__":
    import logger

    logger.init("hems.rasp-water", level=logging.INFO)

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # app.debug = True
    # NOTE: スクリプトの自動リロード停止したい場合は use_reloader=False にする
    app.run(host="0.0.0.0", threaded=True, use_reloader=True)
