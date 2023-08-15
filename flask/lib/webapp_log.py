#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import logging
import os
import sqlite3
import threading
import time
import traceback
from enum import IntEnum
from multiprocessing import Queue
from wsgiref.handlers import format_date_time

import notify_slack
from flask_util import gzipped, support_jsonp
from webapp_config import APP_URL_PREFIX, LOG_DB_PATH, TIMEZONE_OFFSET
from webapp_event import EVENT_TYPE, notify_event

from flask import Blueprint, g, jsonify, request


class APP_LOG_LEVEL(IntEnum):
    INFO = 0
    WARN = 1
    ERROR = 2


blueprint = Blueprint("webapp-log", __name__, url_prefix=APP_URL_PREFIX)

sqlite = None
log_thread = None
log_lock = None
log_queue = None
config = None
should_terminate = False


def init(config_):
    global config
    global sqlite
    global log_lock
    global log_queue
    global log_thread
    global should_terminate

    config = config_

    assert sqlite is None

    sqlite = sqlite3.connect(LOG_DB_PATH, check_same_thread=False)
    sqlite.execute("CREATE TABLE IF NOT EXISTS log(id INTEGER primary key autoincrement, date INTEGER, message TEXT)")
    sqlite.commit()
    sqlite.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    should_terminate = False

    log_lock = threading.Lock()
    log_queue = Queue()
    log_thread = threading.Thread(target=app_log_worker, args=(log_queue,))
    log_thread.start()


def term():
    global sqlite
    global log_thread
    global should_terminate

    if log_thread is None:
        return

    should_terminate = True

    log_thread.join()
    log_thread = None
    sqlite.close()
    sqlite = None


def app_log_impl(message, level):
    global config
    global sqlite

    with log_lock:
        # NOTE: SQLite に記録する時刻はローカルタイムにする
        sqlite.execute(
            'INSERT INTO log VALUES (NULL, DATETIME("now", ?), ?)',
            ["{offset} hours".format(offset=TIMEZONE_OFFSET), message],
        )
        sqlite.execute(
            'DELETE FROM log WHERE date <= DATETIME("now", ?, "-60 days")',
            ["{offset} hours".format(offset=TIMEZONE_OFFSET)],
        )
        sqlite.commit()

        notify_event(EVENT_TYPE.LOG)

    if level == APP_LOG_LEVEL.ERROR:
        if "slack" in config:
            notify_slack.error(
                config["slack"]["bot_token"],
                config["slack"]["error"]["channel"]["name"],
                config["slack"]["from"],
                message,
                config["slack"]["error"]["interval_min"],
            )

        if (os.environ.get("DUMMY_MODE", "false") == "true") and (
            os.environ.get("TEST", "false") != "true"
        ):  # pragma: no cover
            logging.error("This application is terminated because it is in dummy mode.")
            os._exit(-1)


def app_log_worker(log_queue):
    global should_terminate

    sleep_sec = 0.1

    while True:
        if should_terminate:
            break

        try:
            if not log_queue.empty():
                log = log_queue.get()
                app_log_impl(log["message"], log["level"])
        except OverflowError:  # pragma: no cover
            # NOTE: テストする際，freezer 使って日付をいじるとこの例外が発生する
            logging.debug(traceback.format_exc())
            pass
        time.sleep(sleep_sec)


def app_log(message, level=APP_LOG_LEVEL.INFO):
    global log_queue

    if level == APP_LOG_LEVEL.ERROR:
        logging.error(message)
    elif level == APP_LOG_LEVEL.WARN:
        logging.warning(message)
    else:
        logging.info(message)

    # NOTE: 実際のログ記録は別スレッドに任せて，すぐにリターンする
    log_queue.put({"message": message, "level": level})


def get_log(stop_day):
    global sqlite

    cur = sqlite.cursor()
    cur.execute(
        'SELECT * FROM log WHERE date <= DATETIME("now", ?,?) ORDER BY id DESC LIMIT 500',
        # NOTE: デモ用に stop_day 日前までののログしか出さない指定ができるようにるす
        ["{offset} hours".format(offset=TIMEZONE_OFFSET), "-{stop_day} days".format(stop_day=stop_day)],
    )
    return cur.fetchall()


def clear_log():
    global sqlite

    with log_lock:
        cur = sqlite.cursor()
        cur.execute("DELETE FROM log")


@blueprint.route("/api/log_clear", methods=["GET"])
@support_jsonp
def api_log_clear():
    clear_log()
    app_log("🧹 ログがクリアされました。")

    return jsonify({"result": "success"})


@blueprint.route("/api/log_view", methods=["GET"])
@support_jsonp
@gzipped
def api_log_view():
    stop_day = request.args.get("stop_day", 0, type=int)

    # NOTE: @gzipped をつけた場合，キャッシュ用のヘッダを付与しているので，
    # 無効化する．
    g.disable_cache = True

    log = get_log(stop_day)

    if len(log) == 0:
        last_time = time.time()
    else:
        last_time = datetime.datetime.strptime(log[0]["date"], "%Y-%m-%d %H:%M:%S").timestamp()

    response = jsonify({"data": log, "last_time": last_time})

    response.headers["Last-Modified"] = format_date_time(last_time)
    response.make_conditional(request)

    return response


if __name__ == "__main__":
    import logger
    from config import load_config

    logger.init("test", level=logging.INFO)

    init(load_config())

    print(get_log(1))
