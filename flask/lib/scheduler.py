#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import schedule

should_terminate = False


def set_schedule(schedule_setting_list):
    schedule.clear()

    for schedule_setting in schedule_setting_list:
        schedule.every().day.at(schedule_setting["time"]).do(schedule_setting["func"])


def start_scheduler(queue):
    sleep_sec = 1

    while True:
        if not queue.empty():
            set_schedule(queue.get())

        schedule.run_pending()

        if should_terminate:
            logging.info("Terminate scheduler")
            break

        logging.debug("Sleep {sleep_sec} sec...".format(sleep_sec=sleep_sec))
        time.sleep(sleep_sec)


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
    result = pool.apply_async(start_scheduler, (queue,))

    exec_time = datetime.datetime.now() + datetime.timedelta(seconds=5)
    queue.put([{"time": exec_time.strftime("%H:%M:%S"), "func": test_func}])

    # NOTE: 終了するのを待つ
    result.get()
