#!/usr/bin/env python3
# ruff: noqa: S101
import datetime
import json
import logging
import os
import pathlib
import re
import time
from unittest import mock

import my_lib.config
import my_lib.notify.slack
import my_lib.webapp.config
import pytest
from app import create_app
from rasp_water.weather_forecast import get_rain_fall as get_rain_fall_orig

CONFIG_FILE = "config.example.yaml"
SCHEMA_CONFIG = "config.schema"


@pytest.fixture(scope="session", autouse=True)
def env_mock():
    with mock.patch.dict(
        "os.environ",
        {
            "TEST": "true",
            "NO_COLORED_LOGS": "true",
        },
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session")
def config():
    import my_lib.config

    return my_lib.config.load(CONFIG_FILE, pathlib.Path(SCHEMA_CONFIG))


@pytest.fixture(scope="session", autouse=True)
def slack_mock():
    with mock.patch(
        "my_lib.notify.slack.slack_sdk.web.client.WebClient.chat_postMessage",
        return_value=True,
    ) as fixture:
        yield fixture


@pytest.fixture(autouse=True)
def _clear():
    my_lib.notify.slack.interval_clear()
    my_lib.notify.slack.hist_clear()
    ctrl_log_clear()


@pytest.fixture()
def app(config):
    # NOTE: モジュールインポートより前にURL_PREFIXを設定することが重要
    my_lib.webapp.config.URL_PREFIX = "/rasp-water"
    my_lib.webapp.config.init(config)

    with mock.patch.dict("os.environ", {"WERKZEUG_RUN_MAIN": "true"}):
        app = create_app(config, dummy_mode=True)

        yield app

        # NOTE: 特定のテストのみ実行したときのため、ここでも呼ぶ
        test_terminate()


@pytest.fixture()
def client(app, mocker):
    import slack_sdk

    sender_mock = mocker.MagicMock()
    sender_mock.emit.return_value = True
    sender_mock.close.return_value = True

    mocker.patch(
        "fluent.sender.FluentSender",
        return_value=sender_mock,
    )
    mocker.patch(
        "my_lib.notify.slack.slack_sdk.web.client.WebClient.chat_postMessage",
        side_effect=slack_sdk.errors.SlackClientError(),
    )
    mocker.patch("rasp_water.weather_forecast.get_rain_fall", return_value=(False, 0))
    mocker.patch("rasp_water.weather_sensor.get_rain_fall", return_value=(False, 0))

    test_client = app.test_client()

    time.sleep(1)

    schedule_clear(test_client)

    time.sleep(1)
    app_log_clear(test_client)

    yield test_client

    test_client.delete()


def time_test(offset_min=0, offset_hour=0):
    return datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=9))).replace(
        hour=0 + offset_hour, minute=0 + offset_min, second=0
    )


def time_str(time):
    return time.strftime("%H:%M")


def move_to(time_machine, target_time):
    logging.debug("Freeze time at %s", time_str(target_time))

    time_machine.move_to(target_time)


def gen_schedule_data(offset_min=1, is_active=True):
    return [
        {
            "is_active": is_active,
            "time": time_str(time_test(offset_min)),
            "period": 1,
            "wday": [True] * 7,
        }
        for _ in range(2)
    ]


def ctrl_log_check(expect_list, is_strict=True, is_error=True):
    import my_lib.pretty
    import my_lib.rpi

    time.sleep(2)

    hist_list = my_lib.rpi.gpio.hist_get()
    # NOTE: GPIO は1本しか使わないので、チェック対象から外す
    hist_list = [{k: v for k, v in d.items() if k not in "pin_num"} for i, d in enumerate(hist_list)]

    logging.debug(my_lib.pretty.format(hist_list))

    if len(expect_list) == 0:
        assert hist_list == expect_list, "操作されてないはずのバルブが操作されています。"
    elif len(expect_list) >= 2:
        if is_strict:
            assert hist_list == expect_list
        else:
            if is_error and (len(hist_list) > len(expect_list)):
                for _ in range(len(hist_list) - len(expect_list)):
                    expect_list.append(expect_list[-1])

            assert len(hist_list) == len(expect_list)
            for i in range(len(expect_list)):
                if expect_list[i]["state"] == "open":
                    assert (
                        hist_list[i] == expect_list[i]
                    ), f"{i} 番目の操作が期待値と異なります。({hist_list[i]} != {expect_list[i]})"

                if "high_period" in expect_list[i]:
                    assert (hist_list[i] == expect_list[i]) or (
                        hist_list[i]
                        == {
                            "high_period": expect_list[i]["high_period"] - 1,
                            "state": expect_list[i]["state"],
                        }
                    ), f"{i} 番目の操作が期待値と異なります。({hist_list[i]} != {expect_list[i]})"
                else:
                    assert (
                        hist_list[i] == expect_list[i]
                    ), f"{i} 番目の操作が期待値と異なります。({hist_list[i]} != {expect_list[i]})"


def app_log_check(  # noqa: PLR0912, C901
    client,
    expect_list,
    is_strict=True,
):
    import my_lib.pretty

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/log_view")

    log_list = response.json["data"]

    logging.debug(my_lib.pretty.format(log_list))

    if is_strict:
        # NOTE: クリアする直前のログが残っている可能性があるので、+1 でも OK とする
        assert (len(log_list) == len(expect_list)) or (len(log_list) == (len(expect_list) + 1))

    for i, expect in enumerate(reversed(expect_list)):
        if expect == "START_AUTO":
            assert "水やりを開始" in log_list[i]["message"]
        elif expect == "STOP_AUTO":
            assert "水やりを行いました" in log_list[i]["message"]
        elif expect == "STOP_MANUAL":
            assert "水やりを終了します" in log_list[i]["message"]
        elif expect == "SCHEDULE":
            assert "スケジュールを更新" in log_list[i]["message"]
        elif expect == "INVALID":
            assert "スケジュールの指定が不正" in log_list[i]["message"]
        elif expect == "FAIL_AUTO":
            assert "自動実行に失敗" in log_list[i]["message"]
        elif expect == "FAIL_WRITE":
            assert "保存に失敗" in log_list[i]["message"]
        elif expect == "FAIL_READ":
            assert "読み出しに失敗" in log_list[i]["message"]
        elif expect == "PENDING":
            assert "水やりを見合わせます" in log_list[i]["message"]
        elif expect == "FAIL_OVER":
            assert "水が流れすぎています" in log_list[i]["message"]
        elif expect == "FAIL_CLOSE":
            assert "水が流れ続けています" in log_list[i]["message"]
        elif expect == "FAIL_OPEN":
            assert "元栓が閉まっている可能性があります" in log_list[i]["message"]
        elif expect == "CLEAR":
            assert "クリアされました" in log_list[i]["message"]
        else:
            raise AssertionError(f"テストコードのバグです。({expect})")  # noqa: EM102


def schedule_clear(client):
    schedule_data = gen_schedule_data(is_active=False)
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200


def ctrl_log_clear():
    import my_lib.rpi

    my_lib.rpi.gpio.hist_clear()


def _wait_for_valve_operation_completion(max_wait_seconds=3):
    """並列実行でのタイムアウト回避: バルブ操作完了をポーリング"""
    import my_lib.rpi

    start_time = time.time()
    last_hist_count = 0

    while time.time() - start_time < max_wait_seconds:
        current_hist = my_lib.rpi.gpio.hist_get()
        current_count = len(current_hist)

        # バルブ操作履歴に変化があった場合は完了とみなす
        if current_count > last_hist_count:
            last_hist_count = current_count
            # 変化後少し待って安定化
            time.sleep(0.2)
        else:
            # 変化がなければ短時間スリープして再チェック
            time.sleep(0.1)

    # 最大待機時間に達した場合も操作完了とみなす
    logging.debug("Valve operation polling completed after %.1fs", time.time() - start_time)


def app_log_clear(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/log_clear")
    assert response.status_code == 200


def check_notify_slack(message, index=-1):
    import my_lib.notify.slack

    notify_hist = my_lib.notify.slack.hist_get(False)
    logging.debug(notify_hist)

    if message is None:
        assert notify_hist == [], "正常なはずなのに、エラー通知がされています。"
    else:
        assert len(notify_hist) != 0, "異常が発生したはずなのに、エラー通知がされていません。"
        assert notify_hist[index].find(message) != -1, f"「{message}」が Slack で通知されていません。"


######################################################################
def test_liveness(client, config):  # noqa: ARG001
    import healthz

    time.sleep(2)

    assert healthz.check_liveness(
        [
            {
                "name": name,
                "liveness_file": pathlib.Path(config["liveness"]["file"][name]),
                "interval": 10,
            }
            for name in ["scheduler", "valve_control", "flow_notify"]
        ]
    )


def test_time(time_machine, app):  # noqa: ARG001
    import my_lib.time
    import rasp_water.scheduler

    logging.debug("datetime.now()                        = %s", datetime.datetime.now())  # noqa: DTZ005
    logging.debug(
        "datetime.now(%10s)              = %s",
        my_lib.time.get_tz(),
        datetime.datetime.now(my_lib.time.get_zoneinfo()),
    )
    logging.debug(
        "datetime.now().replace(...)           = %s",
        datetime.datetime.now().replace(hour=0, minute=0, second=0),  # noqa: DTZ005
    )
    logging.debug(
        "datetime.now(%10s).replace(...) = %s",
        my_lib.time.get_tz(),
        my_lib.time.now().replace(hour=0, minute=0, second=0),
    )

    move_to(time_machine, time_test(0))

    logging.debug(
        "datetime.now()                        = %s",
        datetime.datetime.now(),  # noqa: DTZ005
    )
    logging.debug("datetime.now(%10s)              = %s", my_lib.time.get_tz(), my_lib.time.now())

    scheduler = rasp_water.scheduler.get_scheduler()
    scheduler.clear()
    job_time_str = time_str(time_test(1))
    logging.debug("set schedule at %s", job_time_str)

    job_add = scheduler.every().day.at(job_time_str, my_lib.time.get_pytz()).do(lambda: True)

    for i, job in enumerate(scheduler.get_jobs()):
        logging.debug("Current schedule [%d]: %s", i, job.next_run)

    idle_sec = scheduler.idle_seconds
    logging.info("Time to next jobs is %.1f sec", idle_sec)
    logging.debug("Next run is %s", job_add.next_run)

    assert abs(idle_sec - 60) < 5


# NOTE: schedule へのテストレポート用
def test_time2(time_machine, app):  # noqa: ARG001
    import time

    import pytz
    import rasp_water.scheduler

    TIMEZONE = datetime.timezone(datetime.timedelta(hours=9), "JST")

    logging.debug("time.localtime()               = %s", time.asctime(time.localtime(time.time())))
    logging.debug("datetime.now()                 = %s", datetime.datetime.now())  # noqa: DTZ005
    logging.debug("datetime.now(JST)              = %s", datetime.datetime.now(TIMEZONE))

    freeze_time = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=9))).replace(
        hour=0, minute=0, second=0
    )

    logging.debug("Freeze time at %s", freeze_time)
    time_machine.move_to(freeze_time)

    logging.debug("time.localtime()               = %s", time.asctime(time.localtime(time.time())))

    logging.debug("datetime.now()                 = %s", datetime.datetime.now())  # noqa: DTZ005
    logging.debug("datetime.now(JST)              = %s", datetime.datetime.now(TIMEZONE))

    scheduler = rasp_water.scheduler.get_scheduler()
    scheduler.clear()

    schedule_time = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=9))).replace(
        hour=0, minute=1, second=0
    )
    schedule_time_str = schedule_time.strftime("%H:%M")
    logging.debug("set schedule at %s", schedule_time_str)

    job_add = scheduler.every().day.at(schedule_time_str, pytz.timezone("Asia/Tokyo")).do(lambda: True)

    idle_sec = scheduler.idle_seconds
    logging.info("Time to next jobs is %.1f sec", idle_sec)
    logging.debug("Next run is %s", job_add.next_run)

    assert abs(idle_sec - 60) < 5


def test_redirect(client):
    response = client.get("/")
    assert response.status_code == 302
    assert re.search(rf"{my_lib.webapp.config.URL_PREFIX}/$", response.location)

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_index(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/")
    assert response.status_code == 200
    assert "散水システム" in response.data.decode("utf-8")

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_index_with_other_status(client, mocker):
    mocker.patch(
        "flask.wrappers.Response.status_code",
        return_value=301,
        new_callable=mocker.PropertyMock,
    )

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 301

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_valve_ctrl_read(client):
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_valve_ctrl_read_fail(client, mocker):
    mocker.patch("rasp_water.valve.get_control_mode", side_effect=RuntimeError())

    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "fail"

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_valve_ctrl_mismatch(client):
    import rasp_water.valve

    # NOTE: Fault injection
    rasp_water.valve.set_control_mode(-10)

    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"
    time.sleep(5)

    ctrl_log_check([{"state": "LOW"}, {"state": "HIGH"}, {"high_period": 1, "state": "LOW"}])
    # NOTE: 強引にバルブを開いているのでアプリのログには記録されない
    app_log_check(client, ["CLEAR", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_manual(client, mocker):
    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)
    # NOTE: ログ表示の際のエラーも仕込んでおく
    mocker.patch("socket.gethostbyaddr", side_effect=RuntimeError())

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"
    assert response.json["remain"] > (period - 2)

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}], is_strict=False
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto(client, mocker):
    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}], is_strict=False
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_rainfall(client, mocker):
    mocker.patch("rasp_water.weather_forecast.get_rain_fall", return_value=(True, 10))

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    # NOTE: ダミーモードの場合は、天気に関わらず水やりする
    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}], is_strict=False
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"], is_strict=False)

    app_log_clear(client)
    ctrl_log_clear()
    logging.error("*********************")

    mocker.patch.dict(os.environ, {"DUMMY_MODE": "false"})
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR", "PENDING"], is_strict=False)
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast(client, mocker):
    mocker.patch("rasp_water.weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    # NOTE: 天気次第で結果が変わるのでログのチェックは行わない
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast_error_1(client, mocker):
    mocker.patch("rasp_water.weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)
    mocker.patch("rasp_water.weather_forecast.get_weather_info_yahoo", return_value=None)

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    # NOTE: get_weather_info_yahoo == None の場合、水やりは行う
    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}], is_strict=False
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast_error_2(client, mocker):
    import rasp_water.weather_forecast

    mocker.patch("rasp_water.weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)

    response_mock = mocker.Mock()
    response_mock.status_code = 404
    mocker.patch.object(rasp_water.weather_forecast.requests, "get", return_value=response_mock)

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}], is_strict=False
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast_error_3(client, mocker):
    import requests

    mocker.patch("rasp_water.weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)

    response = requests.models.Response()
    response.status_code = 500
    mocker.patch("rasp_water.weather_forecast.requests.get", return_value=response)

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}], is_strict=False
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast_error_4(client, mocker):
    import rasp_water.weather_forecast

    mocker.patch("rasp_water.weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)
    mocker.patch.object(rasp_water.weather_forecast.requests, "get", side_effect=RuntimeError())

    period = 2
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": period,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}], is_strict=False
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_flow(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/valve_flow")
    assert response.status_code == 200
    assert "flow" in response.json

    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 0,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/valve_flow")
    assert response.status_code == 200
    assert "flow" in response.json

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR", "STOP_MANUAL"])
    check_notify_slack(None)


def test_event(client):
    import threading

    sse_result = {"response": None, "data": None, "completed": False}

    def sse_request():
        try:
            sse_result["response"] = client.get(
                f"{my_lib.webapp.config.URL_PREFIX}/api/event", query_string={"count": "1"}
            )
            sse_result["data"] = sse_result["response"].data.decode()
            sse_result["completed"] = True
        except Exception:
            logging.exception("SSE request failed")
            sse_result["completed"] = False

    sse_thread = threading.Thread(target=sse_request)
    sse_thread.start()

    time.sleep(0.5)

    app_log_clear(client)

    sse_thread.join(timeout=10)

    assert not sse_thread.is_alive(), "SSE thread should complete after receiving 1 event"
    assert sse_result["completed"], "SSE request should complete successfully"
    assert sse_result["response"] is not None, "SSE should return a response"
    assert sse_result["response"].status_code == 200, "SSE should return status 200"
    assert sse_result["data"], "SSE should receive event data"

    logging.debug("SSE received data: %r", sse_result["data"])

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_inactive(client, time_machine):
    move_to(time_machine, time_test(0))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(is_active=False)
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    move_to(time_machine, time_test(1))
    time.sleep(0.6)

    move_to(time_machine, time_test(2))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(3)
    schedule_data[0]["wday"] = [False] * 7
    schedule_data[1]["wday"] = [False] * 7
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    move_to(time_machine, time_test(3))
    time.sleep(0.6)

    move_to(time_machine, time_test(4))

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR", "SCHEDULE", "SCHEDULE"])
    check_notify_slack(None)


def test_schedule_ctrl_invalid(client):
    schedule_data = gen_schedule_data()
    del schedule_data[0]["period"]
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data.pop(0)
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["is_active"] = "TEST"
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["time"] = "TEST"
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["period"] = "TEST"
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["wday"] = [True] * 5
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["wday"] = ["TEST"] * 7
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    time.sleep(5)

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(
        client,
        [
            "CLEAR",
            "INVALID",
            "INVALID",
            "INVALID",
            "INVALID",
            "INVALID",
            "INVALID",
            "INVALID",
        ],
    )
    check_notify_slack("スケジュールの指定が不正です。")


def test_valve_flow_open_over_1(client, mocker):
    flow_mock = mocker.patch("rasp_water.valve.get_flow")
    flow_mock.return_value = {"flow": 100, "result": "success"}

    mocker.patch("rasp_water.valve.TIME_OVER_FAIL", 0.5)
    # NOTE: これをやっておかないと、後続のテストに影響がでる
    mocker.patch("rasp_water.valve.TIME_ZERO_TAIL", 1)

    period = 3
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}, {"state": "LOW"}],
        is_strict=False,
    )
    app_log_check(client, ["FAIL_OVER"], False)
    check_notify_slack("水が流れすぎています。")

    flow_mock.return_value = {"flow": 0, "result": "success"}
    time.sleep(1)


def test_valve_flow_open_over_2(client, mocker):
    flow_mock = mocker.patch("rasp_water.valve.get_flow")
    flow_mock.return_value = {"flow": 100, "result": "success"}

    mocker.patch("rasp_water.valve.TIME_CLOSE_FAIL", 1)
    # NOTE: これをやっておかないと、後続のテストに影響がでる
    mocker.patch("rasp_water.valve.TIME_ZERO_TAIL", 1)

    period = 3
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    # NOTE: TIME_OVER_FAIL=5秒で流量過多エラーが発生する
    time.sleep(period + 7)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}, {"state": "LOW"}],
        is_strict=False,
    )
    app_log_check(client, ["FAIL_OVER"], False)
    check_notify_slack("水が流れすぎています。")

    # NOTE: テスト後のクリーンアップのために流量を0にする
    flow_mock.return_value = {"flow": 0, "result": "success"}


def test_valve_flow_close_fail(client, mocker):
    # NOTE: Fault injection
    flow_mock = mocker.patch("rasp_water.valve.get_flow")
    flow_mock.return_value = {"flow": 0.1, "result": "success"}
    mocker.patch("rasp_water.valve.TIME_OPEN_FAIL", 1)

    period = 3
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )

    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}, {"state": "LOW"}],
        is_strict=False,
        is_error=True,
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "FAIL_CLOSE"])
    check_notify_slack("バルブを閉めても水が流れ続けています。")

    flow_mock.return_value = {"flow": 0, "result": "success"}
    time.sleep(1)


def test_valve_flow_open_fail(client, mocker):
    # NOTE: Fault injection
    flow_mock = mocker.patch("rasp_water.valve.get_flow")
    flow_mock.return_value = {"flow": 0, "result": "success"}
    mocker.patch("rasp_water.valve.TIME_CLOSE_FAIL", 1)
    mocker.patch("rasp_water.valve.TIME_ZERO_TAIL", 1)

    period = 3
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "HIGH"}, {"high_period": period, "state": "LOW"}],
        is_strict=False,
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO", "FAIL_OPEN"])
    check_notify_slack("元栓が閉まっている可能性があります。")

    flow_mock.return_value = {"flow": 0, "result": "success"}
    time.sleep(1)


def test_valve_flow_read_command_fail(client, mocker):
    import my_lib.footprint
    import rasp_water.valve

    mocker.patch("my_lib.footprint.mtime", side_effect=RuntimeError)

    period = 3
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check([{"state": "LOW"}, {"state": "HIGH"}])
    app_log_check(client, ["CLEAR", "START_AUTO"])
    check_notify_slack(None)

    # NOTE: 後始末をしておく
    my_lib.footprint.clear(rasp_water.valve.STAT_PATH_VALVE_CONTROL_COMMAND)
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 0,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"


def test_schedule_ctrl_execute(client, mocker, time_machine, config):
    import rasp_water.webapp_valve

    rasp_water.webapp_valve.term()
    time.sleep(1)

    time_mock = mocker.patch("my_lib.rpi.gpio_time")

    move_to(time_machine, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(1)

    rasp_water.webapp_valve.init(config)

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(1)

    move_to(time_machine, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(time_machine, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(2)  # 短縮: 天気依存のため詳細チェックなし

    move_to(time_machine, time_test(3))
    time_mock.return_value = time.time()
    time.sleep(2)  # 短縮: 天気依存のため詳細チェックなし

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/valve_flow")
    assert response.status_code == 200
    assert "flow" in response.json

    # NOTE: 天気次第で結果が変わるのでログのチェックは行わない
    check_notify_slack(None)


def test_schedule_ctrl_execute_force(client, mocker, time_machine, config):
    import rasp_water.webapp_valve

    rasp_water.webapp_valve.term()
    time.sleep(1)

    # 並列実行でのタイムアウト回避: タイミング定数を短縮
    mocker.patch("rasp_water.valve.TIME_ZERO_TAIL", 1)  # 5秒 → 1秒
    mocker.patch("rasp_water.valve.TIME_CLOSE_FAIL", 1)  # デフォルト → 1秒
    mocker.patch("rasp_water.valve.TIME_OVER_FAIL", 1)  # デフォルト → 1秒

    mocker.patch("rasp_water.webapp_valve.judge_execute", return_value=True)
    time_mock = mocker.patch("my_lib.rpi.gpio_time")

    move_to(time_machine, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(1)

    rasp_water.webapp_valve.init(config)

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(1)

    move_to(time_machine, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(time_machine, time_test(2))
    time_mock.return_value = time.time()
    # 固定待機の代わりにバルブ状態の完了をポーリング
    _wait_for_valve_operation_completion(3)

    move_to(time_machine, time_test(3))
    time_mock.return_value = time.time()
    # 2回目の操作完了もポーリング
    _wait_for_valve_operation_completion(3)

    ctrl_log_check(
        [{"state": "LOW"}, {"state": "LOW"}, {"state": "HIGH"}, {"state": "LOW", "high_period": 60}]
    )
    app_log_check(client, ["CLEAR", "SCHEDULE", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_schedule_ctrl_execute_pending(client, mocker, time_machine, config):
    import rasp_water.webapp_valve

    rasp_water.webapp_valve.term()
    time.sleep(1)

    mocker.patch("rasp_water.webapp_valve.judge_execute", return_value=False)
    time_mock = mocker.patch("my_lib.rpi.gpio_time")

    move_to(time_machine, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(1)

    rasp_water.webapp_valve.init(config)

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(1)

    move_to(time_machine, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(time_machine, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(2)  # 短縮: judge_execute=False なので処理スキップ

    move_to(time_machine, time_test(3))
    time_mock.return_value = time.time()
    time.sleep(2)  # 短縮: 処理待ちのため

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR", "SCHEDULE"])
    check_notify_slack(None)


def test_schedule_ctrl_error(client, mocker, time_machine, config):
    import rasp_water.webapp_valve

    valve_state_moch = mocker.patch("rasp_water.webapp_valve.set_valve_state")
    valve_state_moch.side_effect = RuntimeError()

    rasp_water.webapp_valve.term()
    time.sleep(1)

    time_mock = mocker.patch("my_lib.rpi.gpio_time")

    move_to(time_machine, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(1)

    rasp_water.webapp_valve.init(config)

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    move_to(time_machine, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(time_machine, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(4)

    move_to(time_machine, time_test(3))
    time_mock.return_value = time.time()

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR", "SCHEDULE", "FAIL_AUTO"])
    check_notify_slack(None)


def test_schedule_ctrl_execute_fail(client, mocker, time_machine, config):
    import rasp_water.webapp_valve

    mocker.patch("rasp_water.scheduler.valve_auto_control_impl", return_value=False)

    rasp_water.webapp_valve.term()
    time.sleep(1)

    time_mock = mocker.patch("my_lib.rpi.gpio_time")

    move_to(time_machine, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(0.6)

    rasp_water.webapp_valve.init(config)

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    move_to(time_machine, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(time_machine, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(4)

    move_to(time_machine, time_test(3))
    time_mock.return_value = time.time()

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR", "SCHEDULE", "FAIL_AUTO"])
    check_notify_slack(None)


def test_schedule_ctrl_read(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_read_fail_1(client, mocker):
    mocker.patch("pickle.load", side_effect=RuntimeError())

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR", "FAIL_READ"])
    check_notify_slack("スケジュール設定の読み出しに失敗しました。")


def test_schedule_ctrl_read_fail_2(client):
    my_lib.webapp.config.SCHEDULE_FILE_PATH.unlink(missing_ok=True)

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_read_fail_3(client, mocker):
    pickle_mock = mocker.patch("pickle.load")

    # 最初に不正データ（配列長1）を返す
    schedule_data = gen_schedule_data()
    schedule_data.pop(0)
    pickle_mock.return_value = schedule_data

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl")
    assert response.status_code == 200
    # 不正データの場合、デフォルト値が返されるので配列長は2
    assert len(response.json) == 2

    # 2回目は正常データを返す
    schedule_data = gen_schedule_data()
    pickle_mock.return_value = schedule_data

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_write_fail(client, mocker):
    from pickle import dump as dump_orig

    mocker.patch("pickle.dump", side_effect=RuntimeError())

    schedule_data = gen_schedule_data(1)
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    # ワーカーがキューを処理してエラーログを出力するまで待機
    time.sleep(1.5)

    mocker.patch("pickle.dump", side_effect=dump_orig)

    # NOTE: 次回のテストに向けて、正常なものに戻しておく
    schedule_data = gen_schedule_data()
    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    # ワーカースレッドがschedule_storeを実行するまで待機
    time.sleep(1.5)

    ctrl_log_check([{"state": "HIGH"}])
    app_log_check(client, ["CLEAR", "FAIL_WRITE", "SCHEDULE", "SCHEDULE"], False)
    check_notify_slack("スケジュール設定の保存に失敗しました。", 0)


def test_schedule_ctrl_validate_fail(client, mocker):
    mocker.patch("rasp_water.scheduler.schedule_validate", return_value=False)

    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_log_view(client, mocker):
    pickle_mock = mocker.patch("pickle.load")
    pickle_mock.return_value = gen_schedule_data(is_active=False)

    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/log_view",
        headers={"Accept-Encoding": "gzip"},
        query_string={
            "callback": "TEST",
        },
    )
    assert response.status_code == 200

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_log_clear(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/log_clear")
    assert response.status_code == 200

    response = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/log_view",
        headers={"Accept-Encoding": "gzip"},
        query_string={
            "callback": "TEST",
        },
    )
    assert response.status_code == 200

    ctrl_log_check([{"state": "LOW"}])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_sysinfo(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/sysinfo")
    assert response.status_code == 200
    assert "date" in response.json
    assert "uptime" in response.json
    assert "load_average" in response.json


def test_snapshot(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/snapshot")
    assert response.status_code == 200
    assert "msg" in response.json
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/snapshot")
    assert response.status_code == 200
    assert "msg" not in response.json


def test_memory(client):
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/memory")
    assert response.status_code == 200
    assert "memory" in response.json


def test_second_str():
    import rasp_water.webapp_valve

    assert rasp_water.webapp_valve.second_str(60) == "1分"
    assert rasp_water.webapp_valve.second_str(61) == "1分1秒"


def test_valve_init(mocker, config, app):  # noqa: ARG001
    import rasp_water.valve
    import rasp_water.webapp_valve

    rasp_water.webapp_valve.term()
    time.sleep(1)

    mocker.patch("pathlib.Path.exists", return_value=True)
    file_mock = mocker.MagicMock()
    file_mock.write.return_value = True
    orig_open = pathlib.Path.open

    def open_mock(self, mode="r", *args, **kwargs):
        if str(self) == config["flow"]["sensor"]["adc"]["scale_file"]:
            return file_mock
        else:
            return orig_open(self, mode, *args, **kwargs)

    mocker.patch("pathlib.Path.open", new=open_mock)

    rasp_water.webapp_valve.init(config)


def test_terminate():
    import my_lib.webapp.log
    import rasp_water.webapp_schedule
    import rasp_water.webapp_valve

    my_lib.webapp.log.term()
    rasp_water.webapp_schedule.term()
    rasp_water.webapp_valve.term()

    # NOTE: 二重に呼んでもエラーにならないことを確認
    my_lib.webapp.log.term()
    rasp_water.webapp_schedule.term()
    rasp_water.webapp_valve.term()
