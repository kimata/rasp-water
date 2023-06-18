# -*- coding: utf-8 -*-
from flask import request, jsonify, Blueprint, current_app
import threading
import logging
from multiprocessing import Queue
import time
import pathlib
import fluent.sender

from webapp_config import APP_URL_PREFIX
from webapp_event import notify_event, EVENT_TYPE
from webapp_log import app_log, APP_LOG_LEVEL
from flask_util import support_jsonp, remote_host
import weather_forecast
import valve

blueprint = Blueprint("rasp-water-valve", __name__, url_prefix=APP_URL_PREFIX)

config = None
should_terminate = False


@blueprint.before_app_first_request
def init():
    global config

    config = current_app.config["CONFIG"]

    flow_stat_queue = Queue()
    valve.init(config, flow_stat_queue)
    threading.Thread(target=flow_notify_worker, args=(flow_stat_queue,)).start()


def send_data(flow):
    global config

    logging.info("Send fluentd: flow = {flow:.1f}".format(flow=flow))
    sender = fluent.sender.FluentSender(
        config["fluent"]["data"]["tag"], host=config["fluent"]["host"]
    )
    sender.emit(
        "rasp", {"hostname": config["fluent"]["data"]["hostname"], "flow": flow}
    )
    sender.close()


def second_str(sec):
    min = 0
    if sec >= 60:
        min = int(sec / 60)
        sec -= min * 60
    sec = int(sec)

    if min != 0:
        if sec == 0:
            return "{min}分".format(min=min)
        else:
            return "{min}分{sec}秒".format(min=min, sec=sec)
    else:
        return "{sec}秒".format(sec=sec)


def flow_notify_worker(queue):
    global should_terminate

    liveness_file = pathlib.Path(config["liveness"]["file"]["flow_notify"])
    liveness_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Start flow notify worker")

    while True:
        if should_terminate:
            break

        if not queue.empty():
            stat = queue.get()

            if stat["type"] == "total":
                app_log(
                    "💧 {time_str}間，約 {water:.2f}L の水やりを行いました。".format(
                        time_str=second_str(stat["period"]), water=stat["total"]
                    )
                )
            elif stat["type"] == "instantaneous":
                send_data(stat["flow"])
            elif stat["type"] == "error":
                app_log(stat["message"], APP_LOG_LEVEL.ERROR)

        liveness_file.touch()

        time.sleep(1)

    logging.info("Terminate flow notify worker")


def get_valve_state():
    try:
        state = valve.get_control_mode()

        return {
            "state": state["mode"].value,
            "remain": state["remain"],
            "result": "success",
        }
    except:
        logging.warning("Failed to get valve control mode")

        return {"state": 0, "remain": 0, "result": "fail"}


def set_valve_state(state, period, auto, host=""):
    is_execute = False
    if state == 1:
        if auto:
            if weather_forecast.get_rain_fall(config):
                app_log("☂ 前後で雨が降る予報があるため、自動での水やりを見合わせます。")

                # NOTE: ダミーモードの場合，とにかく水やりする (CI テストの為)
                if current_app.config["DUMMY_MODE"]:
                    is_execute = True
            else:
                is_execute = True
        else:
            is_execute = True
    else:
        is_execute = True

    if not is_execute:
        notify_event(EVENT_TYPE.CONTROL)
        return get_valve_state()

    if state == 1:
        app_log(
            "{auto}で{period_str}間の水やりを開始します。{by}".format(
                auto="🕑 自動" if auto else "🔧 手動",
                period_str=second_str(period),
                by="(by {})".format(host) if host != "" else "",
            )
        )
        valve.set_control_mode(period)
    else:
        app_log(
            "{auto}で水やりを終了します。{by}".format(
                auto="🕑 自動" if auto else "🔧 手動",
                by="(by {})".format(host) if host != "" else "",
            )
        )
        valve.set_state(valve.VALVE_STATE.CLOSE)

    notify_event(EVENT_TYPE.CONTROL)
    return get_valve_state()


@blueprint.route("/api/valve_ctrl", methods=["GET", "POST"])
@support_jsonp
def api_valve_ctrl():
    cmd = request.args.get("cmd", 0, type=int)
    state = request.args.get("state", 0, type=int)
    period = request.args.get("period", 0, type=int)
    auto = request.args.get("auto", False, type=bool)

    if cmd == 1:
        return jsonify(
            dict(
                {"cmd": "set"},
                **set_valve_state(state, period, auto, remote_host(request))
            )
        )
    else:
        return jsonify(dict({"cmd": "get"}, **get_valve_state()))


@blueprint.route("/api/valve_flow", methods=["GET"])
@support_jsonp
def api_valve_flow():
    return jsonify({"cmd": "get", "flow": valve.get_flow()["flow"]})
