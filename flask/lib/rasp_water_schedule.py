#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import (
    request,
    jsonify,
    current_app,
    Response,
    send_from_directory,
    after_this_request,
    Blueprint,
)
import json
import pickle
import threading
import re

from rasp_water_config import APP_URL_PREFIX, SCHEDULE_DATA_PATH
from rasp_water_log import app_log
from flask_util import support_jsonp, remote_host

blueprint = Blueprint("rasp-water-schedule", __name__, url_prefix=APP_URL_PREFIX)

schedule_lock = threading.Lock()


WDAY_STR = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
WDAY_STR_JA = ["日", "月", "火", "水", "木", "金", "土"]


def schedule_validate(schedule):
    if len(schedule) != 2:
        return False

    for entry in schedule:
        for key in ["is_active", "time", "period", "wday"]:
            if key not in entry:
                return False
            if type(entry["is_active"]) != bool:
                return False
            if not re.compile(r"\d{2}:\d{2}").search(entry["time"]):
                return False
            if type(entry["period"]) != int:
                return False
            if len(entry["wday"]) != 7:
                return False
            for wday_flag in entry["wday"]:
                if type(wday_flag) != bool:
                    return False

    return True


def schedule_store(schedule):
    SCHEDULE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE_DATA_PATH, "wb") as f:
        pickle.dump(schedule, f)


def schedule_load():
    if SCHEDULE_DATA_PATH.exists():
        try:
            with open(SCHEDULE_DATA_PATH, "rb") as f:
                schedule = pickle.load(f)
                if schedule_validate(schedule):
                    return schedule
        except:
            pass

    return [
        {
            "is_active": False,
            "time": "00:00",
            "period": 1,
            "wday": [True] * 7,
        }
    ] * 2


def wday_str_list(wday_list, lang="en"):
    wday_str = WDAY_STR
    if lang == "ja":
        wday_str = WDAY_STR_JA

    return map(
        lambda i: wday_str[i], (i for i in range(len(wday_list)) if wday_list[i])
    )


def schedule_entry_str(entry):
    return "{} 開始 {} 分間 {}".format(
        entry["time"], entry["period"], ",".join(wday_str_list(entry["wday"], "ja"))
    )


def schedule_str(schedule):
    str = []
    for entry in schedule:
        if not entry["is_active"]:
            continue
        str.append(schedule_entry_str(entry))

    return ",\n ".join(str)


@blueprint.route("/api/schedule_ctrl", methods=["GET", "POST"])
@support_jsonp
def api_schedule_ctrl():
    state = request.args.get("set", None)
    if state is not None:
        with schedule_lock:
            schedule = json.loads(state)
            schedule_store(schedule)
            # cron_write(schedule)
            host = remote_host(request)
            app_log(
                "スケジュールを更新しました。\n({schedule} {by})".format(
                    schedule=schedule_str(schedule),
                    by="by {}".format(host) if host != "" else "",
                )
            )

    return jsonify(schedule_load())
