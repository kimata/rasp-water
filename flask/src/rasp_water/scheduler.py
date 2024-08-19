#!/usr/bin/env python3
import logging
import pathlib
import pickle
import re
import threading
import time
import traceback

import my_lib.webapp.config
import my_lib.webapp.log
import rasp_water.webapp_valve
import schedule

RETRY_COUNT = 3

schedule_lock = None
should_terminate = threading.Event()


def init():
    global schedule_lock  # noqa: PLW0603
    schedule_lock = threading.Lock()


def valve_auto_control_impl(config, period):
    try:
        # NOTE: Web 経由だと認証つけた場合に困るので，直接関数を呼ぶ
        rasp_water.webapp_valve.set_valve_state(config, 1, period * 60, True, "scheduler")
        return True

        # logging.debug("Request scheduled execution to {url}".format(url=url))
        # res = requests.post(
        #     url, params={"cmd": 1, "state": 1, "period": period * 60, "auto": True}
        # )
        # logging.debug(res.text)
        # return res.status_code == 200
    except Exception:
        logging.exception("Failed to control valve automatically")

    return False


def valve_auto_control(config, period):
    logging.info("Starts automatic control of the valve")

    for _ in range(RETRY_COUNT):
        if valve_auto_control_impl(config, period):
            return True

    my_lib.webapp.log.info("😵 水やりの自動実行に失敗しました。")
    return False


def schedule_validate(schedule_data):  # noqa: C901, PLR0911
    if len(schedule_data) != 2:
        logging.warning("Count of entry is Invalid: %d", len(schedule_data))
        return False

    for entry in schedule_data:
        for key in ["is_active", "time", "period", "wday"]:
            if key not in entry:
                logging.warning("Does not contain %s", key)
                return False
        if type(entry["is_active"]) is not bool:
            logging.warning("Type of is_active is invalid: %s", type(entry["is_active"]))
            return False
        if not re.compile(r"\d{2}:\d{2}").search(entry["time"]):
            logging.warning("Format of time is invalid: %s", entry["time"])
            return False
        if type(entry["period"]) is not int:
            logging.warning("Type of period is invalid: %s", type(entry["period"]))
            return False
        if len(entry["wday"]) != 7:
            logging.warning("Count of wday is Invalid: %d", len(entry["wday"]))
            return False
        for i, wday_flag in enumerate(entry["wday"]):
            if type(wday_flag) is not bool:
                logging.warning("Type of wday[%d] is Invalid: %s", i, type(entry["wday"][i]))
                return False
    return True


def schedule_store(schedule_data):
    global schedule_lock
    try:
        with schedule_lock:
            my_lib.webapp.config.SCHEDULE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with pathlib.Path(my_lib.webapp.config.SCHEDULE_FILE_PATH).open(mode="wb") as f:
                pickle.dump(schedule_data, f)
    except Exception:
        logging.exception("Failed to save schedule settings.")
        my_lib.webapp.log.error("😵 スケジュール設定の保存に失敗しました。")


def schedule_load():
    global schedule_lock
    if my_lib.webapp.config.SCHEDULE_FILE_PATH.exists():
        try:
            with schedule_lock, pathlib.Path(my_lib.webapp.config.SCHEDULE_FILE_PATH).open(mode="rb") as f:
                schedule_data = pickle.load(f)  # noqa: S301
                if schedule_validate(schedule_data):
                    return schedule_data
        except Exception:
            logging.exception("Failed to load schedule settings.")
            my_lib.webapp.log.error("😵 スケジュール設定の読み出しに失敗しました。")

    return [
        {
            "is_active": False,
            "time": "00:00",
            "period": 1,
            "wday": [True] * 7,
        }
    ] * 2


def set_schedule(config, schedule_data):  # noqa: C901
    schedule.clear()

    for entry in schedule_data:
        if not entry["is_active"]:
            continue

        if entry["wday"][0]:
            schedule.every().sunday.at(entry["time"], my_lib.webapp.config.TIMEZONE_PYTZ).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][1]:
            schedule.every().monday.at(entry["time"], my_lib.webapp.config.TIMEZONE_PYTZ).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][2]:
            schedule.every().tuesday.at(entry["time"], my_lib.webapp.config.TIMEZONE_PYTZ).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][3]:
            schedule.every().wednesday.at(entry["time"], my_lib.webapp.config.TIMEZONE_PYTZ).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][4]:
            schedule.every().thursday.at(entry["time"], my_lib.webapp.config.TIMEZONE_PYTZ).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][5]:
            schedule.every().friday.at(entry["time"], my_lib.webapp.config.TIMEZONE_PYTZ).do(
                valve_auto_control, config, entry["period"]
            )
        if entry["wday"][6]:
            schedule.every().saturday.at(entry["time"], my_lib.webapp.config.TIMEZONE_PYTZ).do(
                valve_auto_control, config, entry["period"]
            )

    for job in schedule.get_jobs():
        logging.info("Next run: %s", job.next_run)

    idle_sec = schedule.idle_seconds()
    if idle_sec is not None:
        hours, remainder = divmod(idle_sec, 3600)
        minutes, seconds = divmod(remainder, 60)

        logging.info(
            "Now is %s, time to next jobs is %d hour(s) %d minute(s) %d second(s)",
            datetime.datetime.now(
                tz=datetime.timezone(datetime.timedelta(hours=my_lib.webapp.config.TIMEZONE_OFFSET))
            ).strftime("%Y-%m-%d %H:%M"),
            hours,
            minutes,
            seconds,
        )

    return idle_sec


def schedule_worker(config, queue):
    global should_terminate

    sleep_sec = 0.25

    liveness_file = pathlib.Path(config["liveness"]["file"]["scheduler"])
    liveness_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Load schedule")
    set_schedule(config, schedule_load())

    logging.info("Start schedule worker")

    i = 0
    while True:
        if should_terminate.is_set():
            schedule.clear()
            break
        try:
            if not queue.empty():
                schedule_data = queue.get()
                set_schedule(config, schedule_data)
                schedule_store(schedule_data)

            schedule.run_pending()
            logging.debug("Sleep %.1f sec...", sleep_sec)
            time.sleep(sleep_sec)
        except OverflowError:  # pragma: no cover
            # NOTE: テストする際，freezer 使って日付をいじるとこの例外が発生する
            logging.debug(traceback.format_exc())

        if i % (10 / sleep_sec) == 0:
            liveness_file.touch()
        i += 1

    logging.info("Terminate schedule worker")


if __name__ == "__main__":
    import datetime
    from multiprocessing import Queue
    from multiprocessing.pool import ThreadPool

    import logger
    import my_lib.webapp.config

    logger.init("test", level=logging.DEBUG)

    def test_func():
        logging.info("TEST")

        should_terminate.set()

    queue = Queue()

    pool = ThreadPool(processes=1)
    result = pool.apply_async(schedule_worker, (queue,))

    exec_time = datetime.datetime.now(my_lib.webapp.config.TIMEZONE) + datetime.timedelta(seconds=5)
    queue.put([{"time": exec_time.strftime("%H:%M"), "func": test_func}])

    # NOTE: 終了するのを待つ
    result.get()
