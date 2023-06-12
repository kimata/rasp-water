#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import jsonify, Blueprint, g
import logging
import threading
import sqlite3
from multiprocessing.pool import ThreadPool

from rasp_water_config import APP_URL_PREFIX, LOG_DB_PATH
from rasp_water_event import notify_event, EVENT_TYPE
from flask_util import support_jsonp, gzipped

blueprint = Blueprint("rasp-water-log", __name__, url_prefix=APP_URL_PREFIX)

sqlite = None
log_lock = None
thread_pool = None


@blueprint.before_app_first_request
def init():
    global sqlite
    global log_lock
    global thread_pool

    sqlite = sqlite3.connect(LOG_DB_PATH, check_same_thread=False)
    sqlite.execute("CREATE TABLE IF NOT EXISTS log(date INT, message TEXT)")
    sqlite.commit()
    sqlite.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    log_lock = threading.Lock()
    thread_pool = ThreadPool(processes=3)


def app_log_impl(message):
    with log_lock:
        sqlite.execute(
            'INSERT INTO log VALUES (DATETIME("now", "localtime"), ?)', [message]
        )
        sqlite.execute(
            'DELETE FROM log WHERE date <= DATETIME("now", "localtime", "-60 days")'
        )
        sqlite.commit()

        notify_event(EVENT_TYPE.LOG)


def app_log(message):
    global thread_pool

    logging.info(message)

    # NOTE: ブラウザからアクセスされる前に再起動される場合．
    if thread_pool is None:
        app_log_impl(message)

    # NOTE: 実際のログ記録は別スレッドに任せて，すぐにリターンする
    thread_pool.apply_async(app_log_impl, (message,))


@blueprint.route("/api/log_clear", methods=["GET"])
@support_jsonp
def api_log_clear():
    with log_lock:
        cur = sqlite.cursor()
        cur.execute("DELETE FROM log")
    app_log("🧹 ログがクリアされました。")

    return jsonify({"result": "success"})


@blueprint.route("/api/log_view", methods=["GET"])
@support_jsonp
@gzipped
def api_log_view():
    g.disable_cache = True

    cur = sqlite.cursor()
    cur.execute("SELECT * FROM log")
    return jsonify({"data": cur.fetchall()[::-1]})


if __name__ == "__main__":
    import logger
    import time

    logger.init("test", level=logging.INFO)

    init()

    for i in range(5):
        app_log("テスト {i}".format(i=i))

    time.sleep(1)

    thread_pool.close()
    thread_pool.terminate()
