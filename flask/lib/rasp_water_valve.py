from flask import (
    request,
    jsonify,
    current_app,
    Response,
    send_from_directory,
    after_this_request,
    Blueprint,
)
import threading
import logging
from multiprocessing import Queue
import time

from rasp_water_config import APP_URL_PREFIX, LOG_DB_PATH, should_terminate
from rasp_water_event import notify_event, EVENT_TYPE
from rasp_water_log import app_log
from flask_util import support_jsonp, remote_host
import valve


blueprint = Blueprint("rasp-water-valve", __name__, url_prefix=APP_URL_PREFIX)


@blueprint.before_app_first_request
def init():
    flow_stat_queue = Queue()
    valve.init(flow_stat_queue)
    threading.Thread(target=flow_notify_worker, args=(flow_stat_queue,)).start()


def second_str(sec):
    sec = int(sec)
    min = 0
    if sec > 60:
        min = int(sec / 60)
        sec -= min * 60

    if min != 0:
        return "{min}分{sec}秒".format(min=min, sec=sec)
    else:
        return "{sec}秒".format(sec=sec)


def flow_notify_worker(queue):
    global should_terminate

    logging.info("Start flow notify worker")

    while True:
        if should_terminate:
            break

        if not queue.empty():
            stat = queue.get()

            if stat["type"] == "total":
                app_log(
                    "{time_str}間，約 {water:.2f}L の水やりを行いました。".format(
                        time_str=second_str(stat["period"]), water=stat["total"]
                    )
                )

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


# def measure_flow_rate():
#     start_time = time.time()
#     measure_list = []

#     if not measure_lock.acquire(True, 0.5):
#         return

#     time.sleep(MEASURE_IGNORE)
#     while not measure_stop.is_set():
#         with open(FLOW_PATH, "r") as f:
#             flow = conv_rawadc_to_flow(int(f.read()))
#             measure_list.append(flow)
#             time.sleep(MEASURE_INTERVAL)

#     stop_time = time.time()
#     while True:
#         with open(FLOW_PATH, "r") as f:
#             flow = conv_rawadc_to_flow(int(f.read()))
#             if flow < 0.1:
#                 break
#             measure_list.append(flow)
#             time.sleep(MEASURE_INTERVAL)

#         if (time.time() - stop_time) > TAIL_SEC:
#             alert("バルブを閉めても水が流れ続けています．")
#             break

#     measure_sum = sum(measure_list)
#     time_delta = (stop_time - start_time) / (len(measure_list) - 1)
#     water_sum = (measure_sum / 60.0) * time_delta
#     log("水やり量は約 {:.2f}L でした。".format(water_sum))

#     if ((stop_time - start_time) > 30) and (water_sum < 1):
#         alert(
#             "元栓が閉まっている可能性があります．(時間: {:.0f}sec, 合計: {:.2f}L)".format(
#                 stop_time - start_time, water_sum
#             )
#         )

#     post_fluentd(start_time, time_delta, measure_list)

#     measure_stop.clear()
#     measure_lock.release()

# def remote_host(request):
#     try:
#         return socket.gethostbyaddr(request.remote_addr)[0]
#     except:
#         return request.remote_addr


def set_valve_state(state, period, auto, host=""):
    if state == 1:
        valve.set_control_mode(period)
    else:
        valve.set_state(valve.VALVE_STATE.CLOSE)

    app_log(
        "{auto}で蛇口を{done}ました。{by}".format(
            auto="自動" if auto else "手動",
            done=["閉じ", "開き"][state],
            by="(by {})".format(host) if host != "" else "",
        )
    )

    #             if is_soil_wet():
    #                 log("雨が降ったため、自動での水やりを見合わせました。")
    #                 return get_valve_state(True)
    #             elif is_rain_forecast():
    #                 log("雨が降る予報があるため、自動での水やりを見合わせました。")
    #                 return get_valve_state(True)

    return get_valve_state()


@blueprint.route("/api/valve_ctrl", methods=["GET", "POST"])
@support_jsonp
def api_valve_ctrl():
    global ctrl_period
    is_worker_start = False

    cmd = request.args.get("cmd", 0, type=int)
    state = request.args.get("state", 0, type=int)
    period = request.args.get("period", 0, type=int)
    auto = request.args.get("auto", False, type=bool)

    if cmd == 1:

        #     with period_lock:
        #         if state == 1:
        #             is_worker_start = ctrl_period != 0
        #             ctrl_period = period
        #         else:
        #             ctrl_period = 0

        #     # NOTE: バルブの制御は ctrl_period の変更後にしないと UI 表示が一瞬おかしくなる．

        result = set_valve_state(state, period, auto, remote_host(request))

        notify_event(EVENT_TYPE.VALVE)

        #     if (state == 1) and (period != 0) and (not is_worker_start):
        #         global manual_ctrl_thread
        #         # if manual_ctrl_thread is not None:
        #         #     manual_ctrl_thread.join()
        #         manual_ctrl_thread = threading.Thread(target=manual_ctrl_worker)
        #         manual_ctrl_thread.start()
        #         thread_pool_add(manual_ctrl_thread)

        return jsonify(dict({"cmd": "set"}, **result))
    else:
        return jsonify(dict({"cmd": "get"}, **get_valve_state()))

    return jsonify(
        {
            "cmd": "set",
            "state": 1,
            "period": period,
            "pending": 0,
            "result": "success",
        }
    )


@blueprint.route("/api/valve_flow", methods=["GET"])
@support_jsonp
def api_valve_flow():
    return jsonify({"cmd": "get", "flow": valve.get_flow()["flow"]})
