#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from enum import IntEnum
import time
import threading
import datetime
import logging
import traceback

from rasp_water_config import STAT_DIR_PATH, should_terminate


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


try:
    import RPi.GPIO as GPIO

    def conv_rawadc_to_flow(adc):
        return (adc * ADC_SCALE_VALUE * FLOW_SCALE_MAX) / 5000.0

    def get_flow():
        with open(ADC_VALUE_PATH, "r") as f:
            return conv_rawadc_to_flow(int(f.read()))

except:
    logging.warning("Using dummy GPIO")
    import random

    # NOTE: Raspbeery Pi 以外で動かした時は，ダミーにする
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
        if STAT_PATH_VALVE_OPEN.exists():
            return 1 + (random.random() - 0.5)
        else:
            return 0


pin_no = GPIO_PIN_DEFAULT
control_lock = threading.Lock()

# NOTE: STAT_PATH_VALVE_CONTROL_COMMAND の内容に基づいて，
# バルブを一定時間開けます
def control_worker():
    global should_terminate

    logging.info("Start valve control worker")

    while True:
        if should_terminate:
            break

        with control_lock:
            try:
                if STAT_PATH_VALVE_CONTROL_COMMAND.exists():
                    with open(STAT_PATH_VALVE_CONTROL_COMMAND, "r") as f:
                        close_time = datetime.datetime.fromtimestamp(int(f.read()))
                        if datetime.datetime.now() > close_time:
                            logging.info("Times is up, close valve")
                            # NOTE: 下記の関数の中で
                            # STAT_PATH_VALVE_CONTROL_COMMAND は削除される
                            set_state(VALVE_STATE.CLOSE)
            except:
                logging.warning(traceback.format_exc())

        time.sleep(1)

    logging.info("Terminate valve control worker")


def init(pin=GPIO_PIN_DEFAULT):
    global pin_no

    pin_no = pin

    set_state(VALVE_STATE.CLOSE)

    threading.Thread(target=control_worker).start()


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

            if close_time > now:
                return {
                    "mode": CONTROL_MODE.TIMER,
                    "remain": (close_time - now).seconds,
                }
            else:
                logging.warn("Timer control of the valve may be broken")
                return {"mode": CONTROL_MODE.TIMER, "remain": 0}
    else:
        return {
            "mode": CONTROL_MODE.IDLE,
        }


if __name__ == "__main__":
    import logger

    logger.init("test", level=logging.INFO)

    init()

    set_state(VALVE_STATE.OPEN)
    time.sleep(0.5)
    logging.info("Flow: {flow:.2f}".format(flow=get_flow()))
    time.sleep(0.5)
    logging.info("Flow: {flow:.2f}".format(flow=get_flow()))
    set_state(VALVE_STATE.CLOSE)
    logging.info("Flow: {flow:.2f}".format(flow=get_flow()))

    set_control_mode(3)
    time.sleep(1)
    logging.info(get_control_mode())
    time.sleep(1)
    logging.info(get_control_mode())
    time.sleep(2)
    logging.info(get_control_mode())

    should_terminate = 1
