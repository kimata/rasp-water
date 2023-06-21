#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import schedule
import time
import pickle
import traceback
import threading
import pathlib
import re

from webapp_config import SCHEDULE_DATA_PATH
from webapp_log import app_log, APP_LOG_LEVEL
import rasp_water_valve

RETRY_COUNT = 3

schedule_lock = None
should_terminate = False


def init():
    global schedule_lock
    schedule_lock = threading.Lock()


def valve_auto_control_impl(config, period):
    try:
        # NOTE: Web 経由だと認証つけた場合に困るので，直接関数を呼ぶ
        rasp_water_valve.set_valve_state(config, 1, period * 60, True, "scueduler")
        return True

        # logging.debug("Request scheduled execution to {url}".format(url=url))
        # res = requests.post(
        #     url, params={"cmd": 1, "state": 1, "period": period * 60, "auto": True}
        # )
        # logging.debug(res.text)
        # return res.status_code == 200
    except:
        logging.warning(traceback.format_exc())
        pass

    return False


def valve_auto_control(config, period):
    logging.info("Starts automatic control of the valve")

    for i in range(RETRY_COUNT):
        if valve_auto_control_impl(config, period):
            return True

    app_log("😵 水やりの自動実行に失敗しました。")
    return False


def schedule_validate(schedule_data):
    if len(schedule_data) != 2:
        return False

    for entry in schedule_data:
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


def schedule_store(schedule_data):
    global schedule_lock
    try:
        with schedule_lock:
            SCHEDULE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SCHEDULE_DATA_PATH, "wb") as f:
                pickle.dump(schedule_data, f)
    except:
        logging.error(traceback.format_exc())
        app_log("😵 スケジュール設定の保存に失敗しました。", APP_LOG_LEVEL.ERROR)
        pass


def schedule_load():
    if SCHEDULE_DATA_PATH.exists():
        try:
            with open(SCHEDULE_DATA_PATH, "rb") as f:
                schedule_data = pickle.load(f)
                if schedule_validate(schedule_data):
                    return schedule_data
        except:
            logging.error(traceback.format_exc())
            app_log("😵 スケジュール設定の読み出しに失敗しました。", APP_LOG_LEVEL.ERROR)
            pass

    return [
        {
            "is_active": False,
            "time": "00:00",
            "period": 1,
            "wday": [True] * 7,
        }
    ] * 2


def set_schedule(config, schedule_data):
    schedule.clear()

    for entry in schedule_data:
        if not entry["is_active"]:
            continue

        if entry["wday"][0]:
            schedule.every().sunday.at(entry["time"]).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][1]:
            schedule.every().monday.at(entry["time"]).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][2]:
            schedule.every().tuesday.at(entry["time"]).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][3]:
            schedule.every().wednesday.at(entry["time"]).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][4]:
            schedule.every().thursday.at(entry["time"]).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][5]:
            schedule.every().friday.at(entry["time"]).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][6]:
            schedule.every().saturday.at(entry["time"]).do(
                valve_auto_control, config, entry["period"]
            )

    for job in schedule.get_jobs():
        logging.info("Next run: {next_run}".format(next_run=job.next_run))


def schedule_worker(config, queue):
    global should_terminate

    sleep_sec = 1

    liveness_file = pathlib.Path(config["liveness"]["file"]["scheduler"])
    liveness_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Load schedule")
    set_schedule(config, schedule_load())

    logging.info("Start schedule worker")

    while True:
        if not queue.empty():
            schedule_data = queue.get()
            set_schedule(config, schedule_data)
            schedule_store(schedule_data)

        schedule.run_pending()

        if should_terminate:
            break

        liveness_file.touch()

        logging.debug("Sleep {sleep_sec} sec...".format(sleep_sec=sleep_sec))
        time.sleep(sleep_sec)

    logging.info("Terminate schedule worker")


if __name__ == "__main__":
    from multiprocessing.pool import ThreadPool
    from multiprocessing import Queue
    import logger
    import datetime

    logger.init("test", level=logging.DEBUG)

    def test_func():
        global should_terminate
        logging.info("TEST")

        should_terminate = True

    queue = Queue()

    pool = ThreadPool(processes=1)
    result = pool.apply_async(schedule_worker, (queue,))

    exec_time = datetime.datetime.now() + datetime.timedelta(seconds=5)
    queue.put([{"time": exec_time.strftime("%H:%M"), "func": test_func}])

    # NOTE: 終了するのを待つ
    result.get()
