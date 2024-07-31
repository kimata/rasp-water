#!/usr/bin/env python3
"""
水やりを自動化するアプリのサーバーです

Usage:
  app.py [-c CONFIG] [-p PORT] [-D] [-d]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します．[default: config.yaml]
  -p PORT           : WEB サーバのポートを指定します．[default: 5000]
  -D                : ダミーモードで実行します．CI テストで利用することを想定しています．
  -d                : デバッグモードで動作します．
"""

import atexit
import logging
import os
import pathlib
import sys

from docopt import docopt
from flask_cors import CORS

from flask import Flask

sys.path.append(str(pathlib.Path(__file__).parent.parent / "lib"))


def create_app(config, dummy_mode=False):
    # NOTE: オプションでダミーモードが指定された場合，環境変数もそれに揃えておく
    if dummy_mode:
        os.environ["DUMMY_MODE"] = "true"
    else:  # pragma: no cover
        os.environ["DUMMY_MODE"] = "false"

    import rasp_water_schedule
    import rasp_water_valve
    import valve
    import webapp_base
    import webapp_event
    import webapp_log
    import webapp_util

    app = Flask("rasp-water")

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        if dummy_mode:
            logging.warning("Set dummy mode")
        else:  # pragma: no cover
            pass

        rasp_water_schedule.init(config)
        rasp_water_valve.init(config)
        webapp_log.init(config)

        def notify_terminate():  # pragma: no cover
            valve.set_state(valve.VALVE_STATE.CLOSE)
            webapp_log.app_log("🏃 アプリを再起動します．")
            webapp_log.term()

        atexit.register(notify_terminate)
    else:  # pragma: no cover
        pass

    CORS(app)

    app.config["CONFIG"] = config
    app.config["DUMMY_MODE"] = dummy_mode

    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

    app.register_blueprint(rasp_water_valve.blueprint)
    app.register_blueprint(rasp_water_schedule.blueprint)

    app.register_blueprint(webapp_base.blueprint_default)
    app.register_blueprint(webapp_base.blueprint)
    app.register_blueprint(webapp_event.blueprint)
    app.register_blueprint(webapp_log.blueprint)
    app.register_blueprint(webapp_util.blueprint)

    # app.debug = True

    return app


if __name__ == "__main__":
    import my_py_lib.config
    import my_py_lib.logger

    args = docopt(__doc__)

    config_file = args["-c"]
    port = args["-p"]
    dummy_mode = args["-D"]
    debug_mode = args["-d"]

    my_py_lib.logger.init("hems.rasp-water", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_py_lib.config.load_config(config_file)

    app = create_app(config, dummy_mode)

    # NOTE: スクリプトの自動リロード停止したい場合は use_reloader=False にする
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=True)  # noqa: S104
