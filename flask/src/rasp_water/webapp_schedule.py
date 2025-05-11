#!/usr/bin/env python3
import json
import threading
import urllib.parse
from multiprocessing import Queue

import flask_cors
import my_lib.flask_util
import my_lib.webapp.config
import my_lib.webapp.event
import my_lib.webapp.log
import rasp_water.scheduler

from flask import Blueprint, jsonify, request, url_for

blueprint = Blueprint("rasp-water-schedule", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)

schedule_lock = threading.Lock()
schedule_queue = None
worker = None

WDAY_STR = ["日", "月", "火", "水", "木", "金", "土"]


def init(config):
    global worker  # noqa: PLW0603
    global schedule_queue  # noqa: PLW0603

    if worker is not None:
        raise ValueError("worker should be None")  # noqa: TRY003, EM101

    schedule_queue = Queue()
    rasp_water.scheduler.init()
    worker = threading.Thread(
        target=rasp_water.scheduler.schedule_worker,
        args=(
            config,
            schedule_queue,
        ),
    )
    worker.start()


def term():
    global worker  # noqa: PLW0603

    if worker is None:
        return

    rasp_water.scheduler.should_terminate.set()
    worker.join()

    worker = None
    rasp_water.scheduler.should_terminate.clear()


def wday_str_list(wday_list):
    wday_str = WDAY_STR
    return [wday_str[i] for i in range(len(wday_list)) if wday_list[i]]


def schedule_entry_str(entry):
    return "{} 開始 {} 分間 {}".format(entry["time"], entry["period"], ",".join(wday_str_list(entry["wday"])))


def schedule_str(schedule):
    str_buf = []
    for entry in schedule:
        if not entry["is_active"]:
            continue
        str_buf.append(schedule_entry_str(entry))

    if len(str_buf) == 0:
        return "∅ 全て無効"

    return "、\n".join(str_buf)


@blueprint.route("/api/schedule_ctrl", methods=["GET", "POST"])
@my_lib.flask_util.support_jsonp
@flask_cors.cross_origin()
def api_schedule_ctrl():
    cmd = request.args.get("cmd", None)
    data = request.args.get("data", None)
    if cmd == "set":
        schedule_data = json.loads(data)

        if not rasp_water.scheduler.schedule_validate(schedule_data):
            my_lib.webapp.log.error("😵 スケジュールの指定が不正です。")
            return jsonify(rasp_water.scheduler.schedule_load())

        with schedule_lock:
            endpoint = urllib.parse.urljoin(
                request.url_root,
                url_for("rasp-water-valve.api_valve_ctrl"),
            )

            for entry in schedule_data:
                entry["endpoint"] = endpoint
            schedule_queue.put(schedule_data)

            # NOTE: 本来は schedule_worker の中だけで呼んでるので不要だけど，
            # レスポンスを schedule_load() で返したいので，ここでも呼ぶ。
            rasp_water.scheduler.schedule_store(schedule_data)

            my_lib.webapp.event.notify_event(my_lib.webapp.event.EVENT_TYPE.SCHEDULE)

            user = my_lib.flask_util.auth_user(request)
            my_lib.webapp.log.info(
                "📅 スケジュールを更新しました。\n{schedule}\n{by}".format(
                    schedule=schedule_str(schedule_data),
                    by=f"by {user}" if user != "" else "",
                )
            )

    return jsonify(rasp_water.scheduler.schedule_load())
