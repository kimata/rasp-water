#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import schedule
import time
import requests
import traceback
import pathlib

from rasp_water_log import app_log

RETRY_COUNT = 3

should_terminate = False


def valve_auto_control_impl(url, period):
    try:
        res = requests.post(
            url, params={"cmd": 1, "state": 1, "period": period * 60, "auto": True}
        )
        return res.status_code == 200
    except:
        logging.warning(traceback.format_exc())
        pass

    return False


def valve_auto_control(url, period):
    logging.info("Starts automatic control of the valve")

    for i in range(RETRY_COUNT):
        if valve_auto_control_impl(url, period):
            return True

    app_log("😵 水やりの自動実行に失敗しました。")
    return False


def set_schedule(schedule_setting_list):
    schedule.clear()

    for schedule_setting in schedule_setting_list:
        if not schedule_setting["is_active"]:
            continue

        func = lambda: valve_auto_control(
            schedule_setting["endpoint"], schedule_setting["period"]
        )
        if schedule_setting["wday"][0]:
            schedule.every().sunday.at(schedule_setting["time"]).do(func)
        if schedule_setting["wday"][1]:
            schedule.every().monday.at(schedule_setting["time"]).do(func)
        if schedule_setting["wday"][2]:
            schedule.every().tuesday.at(schedule_setting["time"]).do(func)
        if schedule_setting["wday"][3]:
            schedule.every().wednesday.at(schedule_setting["time"]).do(func)
        if schedule_setting["wday"][4]:
            schedule.every().thursday.at(schedule_setting["time"]).do(func)
        if schedule_setting["wday"][5]:
            schedule.every().friday.at(schedule_setting["time"]).do(func)
        if schedule_setting["wday"][6]:
            schedule.every().saturday.at(schedule_setting["time"]).do(func)

    for job in schedule.get_jobs():
        logging.info("Next run: {next_run}".format(next_run=job.next_run))


def schedule_worker(config, queue):
    global should_terminate

    sleep_sec = 1

    liveness_file = pathlib.Path(config["liveness"]["file"]["scheduler"])
    liveness_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Start schedule worker")

    while True:
        if not queue.empty():
            set_schedule(queue.get())

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
    import time
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
