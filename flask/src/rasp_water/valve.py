#!/usr/bin/env python3
import inspect
import logging
import os
import pathlib
import threading
import time
import traceback
from builtins import open as valve_open
from enum import IntEnum

import my_lib.rpi
import my_lib.webapp.config

# バルブを一定期間開く際に作られるファイル．
# ファイルの内容はバルブを閉じるべき UNIX 時間．
STAT_PATH_VALVE_CONTROL_COMMAND = my_lib.webapp.config.STAT_DIR_PATH / "valve" / "control" / "command"

# 実際にバルブを開いた際に作られるファイル．
# 実際にバルブを閉じた際に削除される．
STAT_PATH_VALVE_OPEN = my_lib.webapp.config.STAT_DIR_PATH / "valve" / "open"

# 実際にバルブを閉じた際に作られるファイル．
# 実際にバルブを開いた際に削除される．
STAT_PATH_VALVE_CLOSE = my_lib.webapp.config.STAT_DIR_PATH / "valve" / "close"

# 電磁弁制御用の GPIO 端子番号．
# この端子が H になった場合に，水が出るように回路を組んでおく．
GPIO_PIN_DEFAULT = 18


# 流量計の A/D 値が 5V の時の流量
FLOW_SCALE_MAX = 12

# 異常とみなす流量
FLOW_ERROR_TH = 20

# 流量計をモニタする ADC の設定 (ADS1015 のドライバ ti_ads1015 が公開)
ADC_SCALE_PATH = "/sys/bus/iio/devices/iio:device0/in_voltage0_scale"
ADC_SCALE_VALUE = 3

# 流量計のアナログ出力値 (ADS1015 のドライバ ti_ads1015 が公開)
ADC_VALUE_PATH = "/sys/bus/iio/devices/iio:device0/in_voltage0_raw"

# 電磁弁を開いてからこの時間経過しても，水が流れていなかったらエラーにする
TIME_CLOSE_FAIL = 45

# 電磁弁を閉じてからこの時間経過しても，水が流れていたらエラーにする
# (テストで freezegun を使って分単位で制御する関係上，60 より大きい値にしておく)
TIME_OPEN_FAIL = 61

# この時間の間，異常な流量になっていたらエラーにする
TIME_OVER_FAIL = 5

# この時間の間，流量が 0 だったら，今回の計測を停止する．
TIME_ZERO_TAIL = 5


class VALVE_STATE(IntEnum):  # noqa: N801
    OPEN = 1
    CLOSE = 0


class CONTROL_MODE(IntEnum):  # noqa: N801
    TIMER = 1
    IDLE = 0


if (os.environ.get("DUMMY_MODE", "false") != "true") and (
    os.environ.get("TEST", "false") != "true"
):  # pragma: no cover

    def conv_rawadc_to_flow(adc):
        flow = (adc * ADC_SCALE_VALUE * FLOW_SCALE_MAX) / 5000.0
        if flow < 0.01:
            flow = 0

        return flow

    def get_flow():
        try:
            with pathlib.Path(ADC_VALUE_PATH).open(mode="r") as f:
                return {"flow": conv_rawadc_to_flow(int(f.read())), "result": "success"}
        except Exception:
            return {"flow": 0, "result": "fail"}

else:
    import random

    def get_flow():
        if STAT_PATH_VALVE_OPEN.exists():
            if get_flow.prev_flow == 0:
                flow = FLOW_SCALE_MAX
            else:
                flow = max(
                    0,
                    min(
                        get_flow.prev_flow + (random.random() - 0.5) * (FLOW_SCALE_MAX / 5.0),  # noqa: S311
                        FLOW_SCALE_MAX,
                    ),
                )

            get_flow.prev_flow = flow

            return {"flow": flow, "result": "success"}
        else:
            if get_flow.prev_flow > 1:
                get_flow.prev_flow /= 5
            else:
                get_flow.prev_flow = max(0, get_flow.prev_flow - 0.5)

            return {"flow": get_flow.prev_flow, "result": "success"}

    get_flow.prev_flow = 0


pin_no = GPIO_PIN_DEFAULT
worker = None
should_terminate = False


# NOTE: STAT_PATH_VALVE_CONTROL_COMMAND の内容に基づいて，
# バルブを一定時間開けます．
# freezegun を使ったテストのため，この関数の中では，
# time.time() の代わりに my_lib.rpi.gpio_time() を使う．
def control_worker(config, queue):  # noqa: PLR0912, PLR0915, C901
    global should_terminate

    sleep_sec = 0.1

    liveness_file = pathlib.Path(config["liveness"]["file"]["valve_control"])
    liveness_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Start valve control worker")

    time_open_start = None
    time_close = None
    flow = 0
    flow_sum = 0
    count_flow = 0
    count_zero = 0
    count_over = 0
    notify_last_time = None
    notify_last_flow_sum = 0
    notify_last_count = 0
    stop_measure = False

    i = 0
    while True:
        if should_terminate:
            break

        if time_open_start is not None:
            flow = get_flow()["flow"]
            flow_sum += flow
            count_flow += 1

            if (my_lib.rpi.gpio_time() - notify_last_time) > 10:
                # NOTE: 10秒ごとに途中集計を報告する
                queue.put(
                    {
                        "type": "instantaneous",
                        "flow": float(flow_sum - notify_last_flow_sum) / (count_flow - notify_last_count),
                    }
                )

                notify_last_time = my_lib.rpi.gpio_time()
                notify_last_flow_sum = flow_sum
                notify_last_count = count_flow

        # NOTE: 以下の処理はファイルシステムへのアクセスが発生するので，実施頻度を落とす
        if i % 5 == 0:
            if time_open_start is None:
                if STAT_PATH_VALVE_OPEN.exists():
                    # NOTE: バルブが開かれていたら，状態を変更してトータルの水量の集計を開始する
                    time_open_start = my_lib.rpi.gpio_time()
                    notify_last_time = time_open_start
            else:
                if STAT_PATH_VALVE_CONTROL_COMMAND.exists():
                    # NOTE: バルブコマンドが存在したら，閉じる時間をチェックして，必要に応じて閉じる
                    try:
                        with valve_open(STAT_PATH_VALVE_CONTROL_COMMAND) as f:
                            time_to_close = float(f.read())

                            # NOTE: テストの際に freezegun 使う関係で，
                            # 単純な大小比較だけではなく差分絶対値の比較も行う
                            if (my_lib.rpi.gpio_time() > time_to_close) or (
                                abs(my_lib.rpi.gpio_time() - time_to_close) < 0.01
                            ):
                                logging.info("Times is up, close valve")
                                # NOTE: 下記の関数の中で
                                # STAT_PATH_VALVE_CONTROL_COMMAND は削除される
                                set_state(VALVE_STATE.CLOSE)
                                time_close = my_lib.rpi.gpio_time()
                    except Exception:
                        logging.warning(traceback.format_exc())
                if (time_close is None) and STAT_PATH_VALVE_CLOSE.exists():
                    # NOTE: 常にバルブコマンドで制御するので，基本的にここには来ない
                    logging.warning("BUG?")
                    time_close = my_lib.rpi.gpio_time()

            if (time_close is not None) and (time_open_start is not None):
                period_sec = my_lib.rpi.gpio_time() - time_open_start

                # NOTE: バルブが閉じられた後，流量が 0 になっていたらトータル流量を報告する
                if flow < 0.15:
                    count_zero += 1

                if flow > FLOW_ERROR_TH:
                    count_over += 1

                if count_over > TIME_OVER_FAIL:
                    set_state(VALVE_STATE.CLOSE)
                    queue.put({"type": "error", "message": "😵水が流れすぎています。"})

                if count_zero > TIME_ZERO_TAIL:
                    # NOTE: 流量(L/min)の平均を求めてから期間(min)を掛ける
                    total = float(flow_sum) / count_flow * period_sec / 60

                    queue.put(
                        {
                            "type": "total",
                            "period": period_sec,
                            "total": total,
                        }
                    )

                    if (period_sec > TIME_CLOSE_FAIL) and (total < 1):
                        queue.put(
                            {
                                "type": "error",
                                "message": "😵 元栓が閉まっている可能性があります。",
                            }
                        )

                    stop_measure = True
                elif (my_lib.rpi.gpio_time() - time_close) > TIME_OPEN_FAIL:
                    set_state(VALVE_STATE.CLOSE)
                    queue.put(
                        {
                            "type": "error",
                            "message": "😵 バルブを閉めても水が流れ続けています。",
                        }
                    )
                    stop_measure = True

                if stop_measure:
                    stop_measure = False
                    time_open_start = None
                    time_close = None
                    flow_sum = 0
                    count_flow = 0
                    count_zero = 0
                    count_over = 0

                    notify_last_time = None
                    notify_last_flow_sum = 0
                    notify_last_count = 0

        time.sleep(sleep_sec)

        if i % (10 / sleep_sec) == 0:
            liveness_file.touch()
        i += 1

    logging.info("Terminate valve control worker")


def init(config, queue, pin=GPIO_PIN_DEFAULT):
    global should_terminate  # noqa: PLW0603
    global worker  # noqa: PLW0603
    global pin_no  # noqa: PLW0603

    if worker is not None:
        raise ValueError("worker should be None")  # noqa: TRY003, EM101

    should_terminate = False

    pin_no = pin

    set_state(VALVE_STATE.CLOSE)

    logging.info("Setting scale of ADC")
    if pathlib.Path(ADC_SCALE_PATH).exists():
        with pathlib.Path(ADC_SCALE_PATH).open(mode="w") as f:
            f.write(str(ADC_SCALE_VALUE))

    worker = threading.Thread(
        target=control_worker,
        args=(
            config,
            queue,
        ),
    )
    worker.start()


def term():
    global worker  # noqa: PLW0603
    global should_terminate  # noqa: PLW0603

    should_terminate = True
    worker.join()
    worker = None


# NOTE: 実際にバルブを開きます．
def set_state(valve_state):
    global pin_no

    logging.debug(
        "set_state = %s from %s at %s:%d",
        valve_state,
        inspect.stack()[1].function,
        inspect.stack()[1].filename,
        inspect.stack()[1].lineno,
    )

    curr_state = get_state()

    if valve_state != curr_state:
        logging.info("VALVE: %s -> %s", curr_state.name, valve_state.name)

    my_lib.rpi.gpio.setwarnings(False)
    my_lib.rpi.gpio.setmode(my_lib.rpi.gpio.BCM)
    my_lib.rpi.gpio.setup(pin_no, my_lib.rpi.gpio.OUT)
    my_lib.rpi.gpio.output(pin_no, valve_state.value)

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

    my_lib.rpi.gpio.setwarnings(False)
    my_lib.rpi.gpio.setmode(my_lib.rpi.gpio.BCM)
    my_lib.rpi.gpio.setup(pin_no, my_lib.rpi.gpio.OUT)

    if my_lib.rpi.gpio.input(pin_no) == 1:
        return VALVE_STATE.OPEN
    else:
        return VALVE_STATE.CLOSE


def set_control_mode(open_sec):
    logging.info("Open valve for %d sec", open_sec)

    set_state(VALVE_STATE.OPEN)

    time_close = my_lib.rpi.gpio_time() + open_sec

    STAT_PATH_VALVE_CONTROL_COMMAND.parent.mkdir(parents=True, exist_ok=True)

    with pathlib.Path(STAT_PATH_VALVE_CONTROL_COMMAND).open(mode="w") as f:
        f.write(f"{time_close:.3f}")


def get_control_mode():
    if STAT_PATH_VALVE_CONTROL_COMMAND.exists():
        with pathlib.Path(STAT_PATH_VALVE_CONTROL_COMMAND).open() as f:
            time_close = float(f.read())
            time_now = my_lib.rpi.gpio_time()

            if time_close >= time_now:
                return {
                    "mode": CONTROL_MODE.TIMER,
                    "remain": time_close - time_now,
                }
            else:
                if (time_now - time_close) > 1:
                    logging.warning("Timer control of the valve may be broken")
                return {"mode": CONTROL_MODE.TIMER, "remain": 0}
    else:
        return {"mode": CONTROL_MODE.IDLE, "remain": 0}


if __name__ == "__main__":
    from multiprocessing import Queue

    import my_lib.config
    import my_lib.logger

    my_lib.logger.init("test", level=logging.INFO)

    config = my_lib.load()
    queue = Queue()
    init(config, queue)

    set_state(VALVE_STATE.OPEN)
    time.sleep(0.5)
    logging.info("Flow: %.2f", get_flow()["flow"])
    time.sleep(0.5)
    logging.info("Flow: %.2f", get_flow()["flow"])
    set_state(VALVE_STATE.CLOSE)
    logging.info("Flow: %.2f", get_flow()["flow"])

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

    should_terminate = True
