#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from enum import IntEnum
import os
import time
import threading
import datetime
import logging
import traceback
import pathlib

from webapp_config import STAT_DIR_PATH


# バルブを一定期間開く際に作られるファイル．
# ファイルの内容はバルブを閉じるべき UNIX 時間．
STAT_PATH_VALVE_CONTROL_COMMAND = STAT_DIR_PATH / "valve" / "control" / "command"

# 実際にバルブを開いた際に作られるファイル．
# 実際にバルブを閉じた際に削除される．
STAT_PATH_VALVE_OPEN = STAT_DIR_PATH / "valve" / "open"

# 実際にバルブを閉じた際に作られるファイル．
# 実際にバルブを開いた際に削除される．
STAT_PATH_VALVE_CLOSE = STAT_DIR_PATH / "valve" / "close"

# 電磁弁制御用の GPIO 端子番号．
# この端子が H になった場合に，水が出るように回路を組んでおく．
GPIO_PIN_DEFAULT = 18


# 流量計の A/D 値が 5V の時の流量
FLOW_SCALE_MAX = 12

# 流量計をモニタする ADC の設定 (ADS1015 のドライバ ti_ads1015 が公開)
ADC_SCALE_PATH = "/sys/bus/iio/devices/iio:device0/in_voltage0_scale"
ADC_SCALE_VALUE = 3
# 流量計のアナログ出力値 (ADS1015 のドライバ ti_ads1015 が公開)
ADC_VALUE_PATH = "/sys/bus/iio/devices/iio:device0/in_voltage0_raw"


class VALVE_STATE(IntEnum):
    OPEN = 1
    CLOSE = 0


class CONTROL_MODE(IntEnum):
    TIMER = 1
    IDLE = 0


if os.environ["DUMMY_MODE"] != "true":
    import RPi.GPIO as GPIO

    def conv_rawadc_to_flow(adc):
        return (adc * ADC_SCALE_VALUE * FLOW_SCALE_MAX) / 5000.0

    def get_flow():
        try:
            with open(ADC_VALUE_PATH, "r") as f:
                return {"flow": conv_rawadc_to_flow(int(f.read())), "result": "success"}
        except:
            return {"flow": 0, "result": "fail"}

else:
    logging.warning("Using dummy GPIO")
    import random

    # NOTE: 本物の GPIO のように振る舞うダミーのライブラリ
    class GPIO:
        IS_DUMMY = True
        BCM = 0
        OUT = 0
        state = 0

        def setmode(mode):
            return

        def setup(gpio, direction):
            return

        def output(gpio, value):
            GPIO.state = value
            return

        def input(gpio):
            return GPIO.state

        def setwarnings(warnings):
            return

    def get_flow():
        if not STAT_PATH_VALVE_OPEN.exists():
            if get_flow.prev_flow > 1:
                get_flow.prev_flow /= 1.3
            else:
                get_flow.prev_flow = max(0, get_flow.prev_flow - 0.1)

            return {"flow": get_flow.prev_flow, "result": "success"}

        if get_flow.prev_flow == 0:
            flow = random.random() * FLOW_SCALE_MAX
        else:
            flow = max(
                0,
                min(
                    get_flow.prev_flow
                    + (random.random() - 0.5) * (FLOW_SCALE_MAX / 5.0),
                    FLOW_SCALE_MAX,
                ),
            )

        get_flow.prev_flow = flow

        return {"flow": flow, "result": "success"}

    get_flow.prev_flow = 0


pin_no = GPIO_PIN_DEFAULT
should_terminate = False


# NOTE: STAT_PATH_VALVE_CONTROL_COMMAND の内容に基づいて，
# バルブを一定時間開けます
def control_worker(config, queue):
    global should_terminate

    liveness_file = pathlib.Path(config["liveness"]["file"]["valve_control"])
    liveness_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Start valve control worker")

    open_start_time = None
    close_time = None
    flow_sum = 0
    flow_count = 0
    zero_count = 0

    notify_last_time = None
    notify_last_flow_sum = 0
    notify_last_count = 0

    i = 0
    while True:
        if should_terminate:
            break

        if open_start_time is not None:
            flow = get_flow()["flow"]
            flow_sum += flow
            flow_count += 1

            if (datetime.datetime.now() - notify_last_time).total_seconds() > 10:
                # NOTE: 10秒ごとに途中集計を報告する
                queue.put(
                    {
                        "type": "instantaneous",
                        "flow": float(flow_sum - notify_last_flow_sum)
                        / (flow_count - notify_last_count),
                    }
                )

                notify_last_time = datetime.datetime.now()
                notify_last_flow_sum = flow_sum
                notify_last_count = flow_count

        # NOTE: 以下の処理はファイルシステムへのアクセスが発生するので，実施頻度を落とす
        if i % 10 == 0:
            liveness_file.touch()

            if open_start_time is None:
                if STAT_PATH_VALVE_OPEN.exists():
                    # NOTE: バルブが開かれていたら，状態を変更してトータルの水量の集計を開始する
                    open_start_time = datetime.datetime.now()
                    notify_last_time = open_start_time
            else:
                if STAT_PATH_VALVE_CONTROL_COMMAND.exists():
                    # NOTE: バルブコマンドが存在したら，閉じる時間をチェックして，必要に応じて閉じる
                    try:
                        with open(STAT_PATH_VALVE_CONTROL_COMMAND, "r") as f:
                            close_time = datetime.datetime.fromtimestamp(int(f.read()))
                            if datetime.datetime.now() > close_time:
                                logging.info("Times is up, close valve")
                                # NOTE: 下記の関数の中で
                                # STAT_PATH_VALVE_CONTROL_COMMAND は削除される
                                set_state(VALVE_STATE.CLOSE)
                    except:
                        logging.warning(traceback.format_exc())
                if (close_time is None) and STAT_PATH_VALVE_CLOSE.exists():
                    close_time = datetime.datetime.now()

            if (not STAT_PATH_VALVE_OPEN.exists()) and (open_start_time is not None):
                period_sec = (datetime.datetime.now() - open_start_time).total_seconds()

                # NOTE: バルブが閉じられた後，流量が 0 になっていたらトータル流量を報告する
                if flow < 0.1:
                    zero_count += 1

                stop_measure = False
                if zero_count > 2:
                    # NOTE: 流量(L/min)の平均を求めてから期間(min)を掛ける
                    total = float(flow_sum) / flow_count * period_sec / 60

                    queue.put(
                        {
                            "type": "total",
                            "period": period_sec,
                            "total": total,
                        }
                    )

                    if (period_sec > 30) and (total < 1):
                        queue.put({"type": "error", "message": "😵 元栓が閉まっている可能性があります．"})

                    stop_measure = True
                elif (datetime.datetime.now() - close_time).total_seconds() > 60:
                    queue.put({"type": "error", "message": "😵 バルブを閉めても水が流れ続けています．"})
                    stop_measure = True

                if stop_measure:
                    open_start_time = None
                    close_time = None
                    flow_sum = 0
                    flow_count = 0

                    notify_last_time = None
                    notify_last_flow_sum = 0
                    notify_last_count = 0

        time.sleep(0.1)
        i += 1

    logging.info("Terminate valve control worker")


def init(config, queue, pin=GPIO_PIN_DEFAULT):
    global pin_no

    pin_no = pin

    set_state(VALVE_STATE.CLOSE)

    logging.info("Setting scale of ADC")
    if pathlib.Path(ADC_SCALE_PATH).exists():
        with open(ADC_SCALE_PATH, "w") as f:
            f.write(str(ADC_SCALE_VALUE))

    threading.Thread(
        target=control_worker,
        args=(
            config,
            queue,
        ),
    ).start()


# NOTE: 実際にバルブを開きます．
# 現在のバルブの状態と，バルブが現在の状態になってからの経過時間を返します．
def set_state(valve_state):
    global pin_no

    curr_state = get_state()

    if valve_state != curr_state:
        logging.info(
            "VALVE: {curr_state} -> {valve_state}".format(
                curr_state=curr_state.name, valve_state=valve_state.name
            )
        )

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin_no, GPIO.OUT)
    GPIO.output(pin_no, valve_state.value)

    if valve_state == VALVE_STATE.OPEN:
        STAT_PATH_VALVE_CLOSE.unlink(missing_ok=True)
        if not STAT_PATH_VALVE_OPEN.exists():
            STAT_PATH_VALVE_OPEN.parent.mkdir(parents=True, exist_ok=True)
            STAT_PATH_VALVE_OPEN.touch()
    else:
        STAT_PATH_VALVE_OPEN.unlink(missing_ok=True)
        if not STAT_PATH_VALVE_CLOSE.exists():
            STAT_PATH_VALVE_CLOSE.parent.mkdir(parents=True, exist_ok=True)
            STAT_PATH_VALVE_CLOSE.touch()

        STAT_PATH_VALVE_CONTROL_COMMAND.unlink(missing_ok=True)

    return get_state()


# NOTE: 実際のバルブの状態を返します
def get_state():
    global pin_no

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin_no, GPIO.OUT)

    if GPIO.input(pin_no) == 1:
        return VALVE_STATE.OPEN
    else:
        return VALVE_STATE.CLOSE


def set_control_mode(open_sec):
    logging.info("Open valve for {open_sec} sec".format(open_sec=open_sec))

    set_state(VALVE_STATE.OPEN)

    close_time = (
        datetime.datetime.now() + datetime.timedelta(seconds=open_sec)
    ).timestamp()

    STAT_PATH_VALVE_CONTROL_COMMAND.parent.mkdir(parents=True, exist_ok=True)
    with open(STAT_PATH_VALVE_CONTROL_COMMAND, "w") as f:
        f.write("{close_time:.0f}".format(close_time=close_time))


def get_control_mode():
    if STAT_PATH_VALVE_CONTROL_COMMAND.exists():
        with open(STAT_PATH_VALVE_CONTROL_COMMAND, "r") as f:
            close_time = datetime.datetime.fromtimestamp(int(f.read()))
            now = datetime.datetime.now()

            if close_time >= now:
                return {
                    "mode": CONTROL_MODE.TIMER,
                    "remain": int((close_time - now).total_seconds()),
                }
            else:
                if (now - close_time).total_seconds() > 1:
                    logging.warn("Timer control of the valve may be broken")
                return {"mode": CONTROL_MODE.TIMER, "remain": 0}
    else:
        return {"mode": CONTROL_MODE.IDLE, "remain": 0}


if __name__ == "__main__":
    import logger
    from multiprocessing import Queue
    from config import load_config

    logger.init("test", level=logging.INFO)

    config = load_config()
    queue = Queue()
    init(config, queue)

    set_state(VALVE_STATE.OPEN)
    time.sleep(0.5)
    logging.info("Flow: {flow:.2f}".format(flow=get_flow()["flow"]))
    time.sleep(0.5)
    logging.info("Flow: {flow:.2f}".format(flow=get_flow()["flow"]))
    set_state(VALVE_STATE.CLOSE)
    logging.info("Flow: {flow:.2f}".format(flow=get_flow()["flow"]))

    set_control_mode(60)
    time.sleep(1)
    logging.info(get_control_mode())
    time.sleep(1)
    logging.info(get_control_mode())
    time.sleep(2)
    logging.info(get_control_mode())

    while True:
        info = queue.get()
        logging.info(info)

        if info["type"] == "total":
            break

    should_terminate = 1
