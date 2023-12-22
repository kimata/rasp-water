# -*- coding: utf-8 -*-
import logging
import os
import pathlib
import threading
import time
import traceback
from multiprocessing import Queue

import fluent.sender
import valve
import weather_forecast
from flask_cors import cross_origin
from flask_util import auth_user, support_jsonp
from webapp_config import APP_URL_PREFIX
from webapp_event import EVENT_TYPE, notify_event
from webapp_log import APP_LOG_LEVEL, app_log

from flask import Blueprint, current_app, jsonify, request

blueprint = Blueprint("rasp-water-valve", __name__, url_prefix=APP_URL_PREFIX)

worker = None
should_terminate = False


def init(config):
    global worker
    global should_terminate

    assert worker is None

    should_terminate = False

    flow_stat_queue = Queue()
    valve.init(config, flow_stat_queue)
    worker = threading.Thread(target=flow_notify_worker, args=(config, flow_stat_queue))
    worker.start()


def term():
    global should_terminate
    global worker

    if worker is None:
        return

    should_terminate = True
    worker.join()
    worker = None

    valve.term()


def send_data(config, flow):
    logging.info("Send fluentd: flow = {flow:.2f}".format(flow=flow))
    sender = fluent.sender.FluentSender(config["fluent"]["data"]["tag"], host=config["fluent"]["host"])
    sender.emit("rasp", {"hostname": config["fluent"]["data"]["hostname"], "flow": flow})
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


def flow_notify_worker(config, queue):
    global should_terminate

    sleep_sec = 0.1

    liveness_file = pathlib.Path(config["liveness"]["file"]["flow_notify"])
    liveness_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Start flow notify worker")
    i = 0
    while True:
        if should_terminate:
            break

        try:
            if not queue.empty():
                stat = queue.get()

                logging.debug("flow notify = {stat}".format(stat=str(stat)))

                if stat["type"] == "total":
                    app_log(
                        "🚿 {time_str}間，約 {water:.2f}L の水やりを行いました。".format(
                            time_str=second_str(stat["period"]), water=stat["total"]
                        )
                    )
                elif stat["type"] == "instantaneous":
                    send_data(config, stat["flow"])
                elif stat["type"] == "error":
                    app_log(stat["message"], APP_LOG_LEVEL.ERROR)
                else:  # pragma: no cover
                    pass
            time.sleep(sleep_sec)
        except OverflowError:  # pragma: no cover
            # NOTE: テストする際，freezer 使って日付をいじるとこの例外が発生する
            logging.debug(traceback.format_exc())
            pass

        if i % (10 / sleep_sec) == 0:
            liveness_file.touch()
        i += 1

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


def judge_execute(config, state, auto):
    if (state != 1) or (not auto):
        return True

    if weather_forecast.get_rain_fall(config):
        # NOTE: ダミーモードの場合，とにかく水やりする (CI テストの為)
        if os.environ.get("DUMMY_MODE", "false") == "true":
            return True
        else:
            app_log("☂ 前後で雨が降る予報があるため、自動での水やりを見合わせます。")
            return False

    return True


def set_valve_state(config, state, period, auto, host=""):
    is_execute = judge_execute(config, state, auto)

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
@cross_origin()
def api_valve_ctrl():
    cmd = request.args.get("cmd", 0, type=int)
    state = request.args.get("state", 0, type=int)
    period = request.args.get("period", 0, type=int)
    auto = request.args.get("auto", False, type=bool)

    config = current_app.config["CONFIG"]

    if cmd == 1:
        user = auth_user(request)
        return jsonify(dict({"cmd": "set"}, **set_valve_state(config, state, period, auto, user)))
    else:
        return jsonify(dict({"cmd": "get"}, **get_valve_state()))


@blueprint.route("/api/valve_flow", methods=["GET"])
@support_jsonp
@cross_origin()
def api_valve_flow():
    return jsonify({"cmd": "get", "flow": valve.get_flow()["flow"]})
