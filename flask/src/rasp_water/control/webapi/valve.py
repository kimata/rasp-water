#!/usr/bin/env python3
import logging
import multiprocessing
import os
import pathlib
import threading
import time
import traceback

import flask_cors
import fluent.sender
import my_lib.flask_util
import my_lib.footprint
import my_lib.webapp.config
import my_lib.webapp.event
import my_lib.webapp.log
import rasp_water.control.valve
import rasp_water.control.weather_forecast
import rasp_water.control.weather_sensor

import flask

blueprint = flask.Blueprint("rasp-water-valve", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)

worker = None
flow_stat_manager = None
should_terminate = threading.Event()


def init(config):
    global worker  # noqa: PLW0603
    global flow_stat_manager  # noqa: PLW0603

    if worker is not None:
        raise ValueError("worker should be None")  # noqa: TRY003, EM101

    if flow_stat_manager is not None:
        flow_stat_manager.shutdown()

    flow_stat_manager = multiprocessing.Manager()
    flow_stat_queue = flow_stat_manager.Queue()
    rasp_water.control.valve.init(config, flow_stat_queue)
    worker = threading.Thread(target=flow_notify_worker, args=(config, flow_stat_queue))
    worker.start()


def term():
    global worker  # noqa: PLW0603

    if worker is None:
        return

    should_terminate.set()
    worker.join()

    worker = None
    should_terminate.clear()

    rasp_water.control.valve.term()


def send_data(config, flow):
    logging.info("Send fluentd: flow = %.2f", flow)
    sender = fluent.sender.FluentSender(config["fluent"]["data"]["tag"], host=config["fluent"]["host"])
    sender.emit("rasp", {"hostname": config["fluent"]["data"]["hostname"], "flow": flow})
    sender.close()


def second_str(sec):
    minute = 0
    if sec >= 60:
        minute = int(sec / 60)
        sec -= minute * 60
    sec = int(sec)

    if minute != 0:
        if sec == 0:
            return f"{minute}分"
        else:
            return f"{minute}分{sec}秒"
    else:
        return f"{sec}秒"


def flow_notify_worker(config, queue):
    global should_terminate

    sleep_sec = 0.1

    liveness_file = pathlib.Path(config["liveness"]["file"]["flow_notify"])

    logging.info("Start flow notify worker")
    i = 0
    while True:
        if should_terminate.is_set():
            break

        try:
            if not queue.empty():
                stat = queue.get()

                logging.debug("flow notify = %s", str(stat))

                if stat["type"] == "total":
                    my_lib.webapp.log.info(
                        "🚿 {time_str}間、約 {water:.2f}L の水やりを行いました。".format(
                            time_str=second_str(stat["period"]), water=stat["total"]
                        )
                    )
                    
                    # メトリクス記録
                    try:
                        import rasp_water.metrics.collector
                        operation_type = "auto" if stat.get("auto", False) else "manual"
                        rasp_water.metrics.collector.record_watering(
                            operation_type=operation_type,
                            duration_seconds=stat["period"],
                            volume_liters=stat["total"],
                            metrics_data_path=config["metrics"]["data"]
                        )
                    except Exception as e:
                        logging.warning("Failed to record watering metrics: %s", e)
                elif stat["type"] == "instantaneous":
                    send_data(config, stat["flow"])
                elif stat["type"] == "error":
                    my_lib.webapp.log.error(stat["message"])
                    
                    # エラーメトリクス記録
                    try:
                        import rasp_water.metrics.collector
                        rasp_water.metrics.collector.record_error(
                            error_type="valve_control",
                            error_message=stat["message"],
                            metrics_data_path=config["metrics"]["data"]
                        )
                    except Exception as e:
                        logging.warning("Failed to record error metrics: %s", e)
                else:  # pragma: no cover
                    pass
            time.sleep(sleep_sec)
        except OverflowError:  # pragma: no cover
            # NOTE: テストする際、freezer 使って日付をいじるとこの例外が発生する
            logging.debug(traceback.format_exc())

        if i % (10 / sleep_sec) == 0:
            my_lib.footprint.update(liveness_file)

        i += 1

    logging.info("Terminate flow notify worker")


def get_valve_state():
    try:
        state = rasp_water.control.valve.get_control_mode()

        return {
            "state": state["mode"].value,
            "remain": state["remain"],
            "result": "success",
        }
    except Exception:
        logging.warning("Failed to get valve control mode")

        return {"state": 0, "remain": 0, "result": "fail"}


def judge_execute(config, state, auto):
    if (state != 1) or (not auto):
        return True

    rainfall_judge, rain_fall_sum = rasp_water.control.weather_sensor.get_rain_fall(config)
    if rainfall_judge:
        # NOTE: ダミーモードの場合、とにかく水やりする (CI テストの為)
        if os.environ.get("DUMMY_MODE", "false") == "true":
            return True

        my_lib.webapp.log.info(
            f"☂ 前回の水やりから {rain_fall_sum:.0f}mm の雨が降ったため、自動での水やりを見合わせます。"
        )
        return False

    rainfall_judge, rain_fall_sum = rasp_water.control.weather_forecast.get_rain_fall(config)

    if rainfall_judge:
        # NOTE: ダミーモードの場合、とにかく水やりする (CI テストの為)
        if os.environ.get("DUMMY_MODE", "false") == "true":
            return True

        my_lib.webapp.log.info(
            f"☂ 前後で {rain_fall_sum:.0f}mm の雨が降る予報があるため、自動での水やりを見合わせます。"
        )
        return False

    return True


def set_valve_state(config, state, period, auto, host=""):
    is_execute = judge_execute(config, state, auto)

    if not is_execute:
        my_lib.webapp.event.notify_event(my_lib.webapp.event.EVENT_TYPE.CONTROL)
        return get_valve_state()

    if state == 1:
        my_lib.webapp.log.info(
            "{auto}で{period_str}間の水やりを開始します。{by}".format(
                auto="🕑 自動" if auto else "🔧 手動",
                period_str=second_str(period),
                by=f"(by {host})" if host != "" else "",
            )
        )
        rasp_water.control.valve.set_control_mode(period, auto)
    else:
        my_lib.webapp.log.info(
            "{auto}で水やりを終了します。{by}".format(
                auto="🕑 自動" if auto else "🔧 手動",
                by=f"(by {host})" if host != "" else "",
            )
        )
        rasp_water.control.valve.set_state(rasp_water.control.valve.VALVE_STATE.CLOSE)

    my_lib.webapp.event.notify_event(my_lib.webapp.event.EVENT_TYPE.CONTROL)
    return get_valve_state()


@blueprint.route("/api/valve_ctrl", methods=["GET", "POST"])
@my_lib.flask_util.support_jsonp
@flask_cors.cross_origin()
def api_valve_ctrl():
    cmd = flask.request.args.get("cmd", 0, type=int)
    state = flask.request.args.get("state", 0, type=int)
    period = flask.request.args.get("period", 0, type=int)
    auto = flask.request.args.get("auto", False, type=bool)

    config = flask.current_app.config["CONFIG"]

    if cmd == 1:
        user = my_lib.flask_util.auth_user(flask.request)
        return flask.jsonify(dict({"cmd": "set"}, **set_valve_state(config, state, period, auto, user)))
    else:
        return flask.jsonify(dict({"cmd": "get"}, **get_valve_state()))


@blueprint.route("/api/valve_flow", methods=["GET"])
@my_lib.flask_util.support_jsonp
@flask_cors.cross_origin()
def api_valve_flow():
    config = flask.current_app.config["CONFIG"]

    return flask.jsonify({"cmd": "get", "flow": rasp_water.control.valve.get_flow(config["flow"]["offset"])["flow"]})
