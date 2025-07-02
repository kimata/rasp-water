#!/usr/bin/env python3
"""
水やりを自動化するアプリのサーバーです

Usage:
  app.py [-c CONFIG] [-p PORT] [-D] [-d]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -p PORT           : WEB サーバのポートを指定します。[default: 5000]
  -d                : ダミーモードで実行します。CI テストで利用することを想定しています。
  -D                : デバッグモードで動作します。
"""

import atexit
import logging
import os
import signal

import flask_cors

import flask

import my_lib.webapp.base
import my_lib.webapp.event
import my_lib.webapp.log
import my_lib.webapp.util
import my_lib.proc_util
import rasp_water.control.webapi.schedule
import rasp_water.control.webapi.valve
import rasp_water.control.webapi.test.time
import rasp_water.metrics.webapi.page


SCHEMA_CONFIG = "config.schema"

def term():
    import rasp_water.control.scheduler

    rasp_water.control.scheduler.term()

    # 子プロセスを終了
    my_lib.proc_util.kill_child()

    # プロセス終了
    logging.info("Graceful shutdown completed")
    os._exit(0)


def sig_handler(num, frame):  # noqa: ARG001
    global should_terminate

    logging.warning("receive signal %d", num)

    if num == signal.SIGTERM:
        term()


def create_app(config, dummy_mode=False):
    # NOTE: オプションでダミーモードが指定された場合、環境変数もそれに揃えておく
    if dummy_mode:
        os.environ["DUMMY_MODE"] = "true"
    else:  # pragma: no cover
        os.environ["DUMMY_MODE"] = "false"

    # NOTE: テストのため、環境変数 DUMMY_MODE をセットしてからロードしたいのでこの位置
    import my_lib.webapp.config

    my_lib.webapp.config.URL_PREFIX = "/rasp-water"
    my_lib.webapp.config.init(config)

    app = flask.Flask("rasp-water")

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        if dummy_mode:
            logging.warning("Set dummy mode")
        else:  # pragma: no cover
            pass

        rasp_water.control.webapi.schedule.init(config)
        rasp_water.control.webapi.valve.init(config)
        my_lib.webapp.log.init(config)

        def notify_terminate():  # pragma: no cover
            rasp_water.control.valve.set_state(rasp_water.control.valve.VALVE_STATE.CLOSE)
            my_lib.webapp.log.info("🏃 アプリを再起動します。")
            my_lib.webapp.log.term()

        atexit.register(notify_terminate)
    else:  # pragma: no cover
        pass

    flask_cors.CORS(app)

    app.config["CONFIG"] = config
    app.config["DUMMY_MODE"] = dummy_mode

    app.json.compat = True

    app.register_blueprint(rasp_water.control.webapi.valve.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(rasp_water.control.webapi.schedule.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(rasp_water.metrics.webapi.page.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)

    if dummy_mode:
        app.register_blueprint(rasp_water.control.webapi.test.time.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)

    app.register_blueprint(my_lib.webapp.base.blueprint_default)
    app.register_blueprint(my_lib.webapp.base.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.event.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.log.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.util.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)

    my_lib.webapp.config.show_handler_list(app)

    return app


if __name__ == "__main__":
    import pathlib

    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    port = args["-p"]
    dummy_mode = args["-d"]
    debug_mode = args["-D"]

    my_lib.logger.init("hems.rasp-water", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file, pathlib.Path(SCHEMA_CONFIG))

    app = create_app(config, dummy_mode)

    signal.signal(signal.SIGTERM, sig_handler)

    # Flaskアプリケーションを実行
    try:
        # NOTE: スクリプトの自動リロード停止したい場合は use_reloader=False にする
        app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=True, debug=debug_mode)  # noqa: S104
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down...")
        sig_handler(signal.SIGINT, None)
    finally:
        term()
