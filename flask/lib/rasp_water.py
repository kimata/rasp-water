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

from functools import wraps
import re
import socket
import sqlite3
import subprocess
import threading
import datetime
import time
import json
from crontab import CronTab
import os
import functools
import gzip
from io import BytesIO
from fluent import sender
import tracemalloc


from rasp_water_config import APP_URL_PREFIX, ANGULAR_DIST_PATH
from flask_util import support_jsonp, gzipped

# import rasp_water_util

# try:
#     import RPi.GPIO as GPIO
# except:
#     # NOTE: Raspbeery Pi 以外で動かした時は，ダミーにする
#     class GPIO:
#         BCM = 0
#         OUT = 0
#         LOW = 0

#         def setmode(dummy):
#             return

#         def setwarnings(dummy):
#             return

#         def setup(dummy1, dummy2):
#             return

#         def output(dummy1, dummy2):
#             return


# GPIO.setmode(GPIO.BCM)
# GPIO.setwarnings(False)

# from soilwet_check import is_soil_wet
# from forecast_check import is_rain_forecast

# # 電磁弁が接続されている GPIO
# CTRL_GPIO = 18


# # 流量計の積算から除外する期間[秒]
# MEASURE_IGNORE = 5
# # 流量計を積算する間隔[秒]
# MEASURE_INTERVAL = 0.3
# # バルブを止めてからも水が出流れていると想定される時間[秒]
# TAIL_SEC = 120

# LOG_DATABASE = "/var/log/rasp-water.db"
# CRONTAB = "/var/spool/cron/crontabs/root"


# FLUENTD_HOST = "columbia.green-rabbit.net"


# SCHEDULE_MARKER = "WATER SCHEDULE"
# WATER_CTRL_CMD = os.path.abspath(
#     os.path.join(os.path.dirname(__file__), "..", "script", "water_ctrl.py")
# )
# SYNC_OVERLAY_CMD = os.path.abspath(
#     os.path.join(os.path.dirname(__file__), "..", "script", "sync_overlay.zsh")
# )


# tracemalloc.start()
# snapshot_prev = None

rasp_water = Blueprint("rasp-water", __name__, url_prefix=APP_URL_PREFIX)

# sqlite = sqlite3.connect(LOG_DATABASE, check_same_thread=False)
# sqlite.execute("CREATE TABLE IF NOT EXISTS log(date INT, message TEXT)")
# sqlite.commit()
# sqlite.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

# thread_pool_lock = threading.Lock()
# event_lock = threading.Lock()
# schedule_lock = threading.Lock()
# measure_lock = threading.Lock()
# ctrl_lock = threading.Lock()
# period_lock = threading.Lock()
# measure_stop = threading.Event()
# ctrl_period = 0

# log_thread = None
# manual_ctrl_thread = None
# measure_flow_thread = None


# thread_pool = []


# def thread_pool_add(new_thread):
#     global thread_pool
#     with thread_pool_lock:
#         active_pool = [new_thread]
#         for thread in thread_pool:
#             thread.join(0.001)
#             if thread.is_alive():
#                 active_pool.append(thread)
#         thread_pool = active_pool


# def parse_cron_line(line):
#     match = re.compile(
#         "^(#?)\s*(\d{{1,2}})\s+(\d{{1,2}})\s.+\s(\S+)\s+{}\s+(\d+)".format(
#             re.escape(WATER_CTRL_CMD)
#         )
#     ).search(str(line))

#     if match:
#         mg = match.groups()
#         wday_str_list = mg[3].split(",")

#         return {
#             "is_active": mg[0] == "",
#             "time": "{:02}:{:02}".format(int(mg[2]), int(mg[1])),
#             "period": int(mg[4]),
#             "wday": list(map(lambda str: str in wday_str_list, WDAY_STR)),
#         }

#     return None


# def cron_create_job(cron, schedule, i):
#     job = cron.new(command="{} {}".format(WATER_CTRL_CMD, schedule[i]["period"]))
#     time = schedule[i]["time"].split(":")
#     time.reverse()
#     job.setall("{} {} * * *".format(*time))
#     job.dow.on(*(wday_str_list(schedule[i]["wday"])))
#     job.set_comment("{} {}".format(SCHEDULE_MARKER, i))
#     job.enable(schedule[i]["is_active"])

#     return job


# def cron_write(schedule):
#     cron = CronTab(user=True)
#     new_cron = CronTab()

#     # NOTE: remove* 系のメソッドを使うとどんどん空行が増えるので，
#     # append して更新を行う．

#     for job in cron:
#         for i in range(2):
#             if re.compile("{} {}".format(re.escape(SCHEDULE_MARKER), i)).search(
#                 job.comment
#             ):
#                 job = cron_create_job(cron, schedule, i)
#                 schedule[i]["append"] = True
#         # NOTE: Ubuntu の場合 apt でインストールした python-crontab
#         # では動かない．pip3 でインストールした python-crontab が必要．
#         new_cron.append(job)

#     for i in range(2):
#         if "append" not in schedule[i]:
#             new_cron.append(cron_create_job(cron, schedule, i))

#     new_cron.write_to_user(user=True)

#     # すぐに反映されるよう，明示的にリロード
#     subprocess.check_call(["sudo", "/etc/init.d/cron", "restart"])
#     # Read only にしてある root filesystem にも反映
#     subprocess.check_call([SYNC_OVERLAY_CMD, CRONTAB])

#     with event_lock:
#         event_count[EVENT_TYPE_SCHEDULE] += 1


# def alert(message):
#     subprocess.call(
#         'echo "{}" | mail -s "rasp-water アラート" root'.format(message), shell=True
#     )


# def post_fluentd(start_time, time_delta, measure_list):
#     fluentd = sender.FluentSender("sensor", host=FLUENTD_HOST)

#     hostname = os.uname()[1]
#     measure_time = start_time
#     post_time = int(measure_time)
#     sec_sum = 0p
#     for measure in measure_list:
#         if int(measure_time) != post_time:
#             # NOTE: 秒単位で積算してから Fluentd に投げる
#             fluentd.emit_with_time(
#                 "water", post_time, {"hostname": hostname, "water": sec_sum}
#             )
#             post_time = int(measure_time)
#             sec_sum = 0.0
#         sec_sum += (measure / 60.0) * time_delta
#         measure_time += time_delta
#     fluentd.emit_with_time("water", post_time, {"hostname": hostname, "water": sec_sum})
#     fluentd.close()


def app_init():
    return 0


#     subprocess.call(
#         'echo "{} に再起動しました．" | mail -s "rasp-water 再起動" root'.format(
#             datetime.datetime.today()
#         ),
#         shell=True,
#     )

#     log("アプリが再起動しました．")

#     print("GPIO を L に初期化します...")
#     GPIO.setup(CTRL_GPIO, GPIO.OUT)
#     gpio_set_state(CTRL_GPIO, GPIO.LOW)

#     print("ADC の設定を行います...")
#     if os.path.exists(SCALE_PATH):
#         with open(SCALE_PATH, "w") as f:
#             f.write(str(SCALE_VALUE))
#     else:
#         print("\u001b[31m!!WARNING!! ADC が見つかりません．デバッグ目的と見なして動作を継続します...\u001b[00m")


@rasp_water.route("/", defaults={"filename": "index.html"})
@rasp_water.route("/<path:filename>")
@gzipped
def angular(filename):
    return send_from_directory(ANGULAR_DIST_PATH, filename)
