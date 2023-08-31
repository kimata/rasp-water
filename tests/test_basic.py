#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
import os
import pathlib
import re
import sys
import time
from unittest import mock

import pytest

sys.path.append(str(pathlib.Path(__file__).parent.parent / "flask" / "app"))
sys.path.append(str(pathlib.Path(__file__).parent.parent / "flask" / "lib"))

from weather_forecast import get_rain_fall as get_rain_fall_orig
from webapp_config import TIMEZONE, TIMEZONE_PYTZ

from app import create_app

CONFIG_FILE = "config.example.yaml"


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


@pytest.fixture(scope="session", autouse=True)
def slack_mock():
    with mock.patch(
        "notify_slack.slack_sdk.web.client.WebClient.chat_postMessage",
        retunr_value=True,
    ) as fixture:
        yield fixture


@pytest.fixture(scope="function", autouse=True)
def clear():
    import notify_slack

    notify_slack.interval_clear()
    notify_slack.hist_clear()


@pytest.fixture(scope="session")
def app():
    with mock.patch.dict("os.environ", {"WERKZEUG_RUN_MAIN": "true"}):
        app = create_app(CONFIG_FILE, dummy_mode=True)

        yield app

        # NOTE: 特定のテストのみ実行したときのため，ここでも呼ぶ
        test_terminate()


@pytest.fixture(scope="function")
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
        "notify_slack.slack_sdk.web.client.WebClient.chat_postMessage",
        side_effect=slack_sdk.errors.SlackClientError(),
    )
    mocker.patch(
        "weather_forecast.get_rain_fall",
        return_value=False,
    )

    test_client = app.test_client()

    time.sleep(1)
    schedule_clear(test_client)
    time.sleep(1)
    app_log_clear(test_client)
    app_log_check(test_client, [])
    ctrl_log_clear()

    yield test_client

    test_client.delete()


def time_test(offset_min=0):
    return datetime.datetime.now(TIMEZONE).replace(hour=0, minute=0 + offset_min, second=0)


def time_str(time):
    return time.strftime("%H:%M")


def move_to(freezer, target_time):
    freezer.move_to(target_time + datetime.timedelta(hours=+9))


def gen_schedule_data(offset_min=1):
    return [
        {
            "is_active": True,
            "time": time_str(time_test(offset_min)),
            "period": 1,
            "wday": [True] * 7,
        }
        for _ in range(2)
    ]


def ctrl_log_check(expect_list, is_strict=True, is_error=True):
    import logging

    import valve

    hist_list = valve.GPIO.hist_get()

    logging.debug(hist_list)

    if len(expect_list) == 0:
        assert hist_list == expect_list, "操作されてないはずのバルブが操作されています。"
    elif len(expect_list) >= 2:
        if is_strict:
            assert hist_list == expect_list
        else:
            if is_error and (len(hist_list) > len(expect_list)):
                for i in range(len(hist_list) - len(expect_list)):
                    expect_list.append(expect_list[-1])

            assert len(hist_list) == len(expect_list)
            for i in range(len(expect_list)):
                if expect_list[i]["state"] == "open":
                    assert hist_list[i] == expect_list[i], "{i} 番目の操作が期待値と異なります。".format(i=i)
                else:
                    if "period" in expect_list[i]:
                        assert (hist_list[i] == expect_list[i]) or (
                            hist_list[i]
                            == {
                                "period": expect_list[i]["period"] - 1,
                                "state": expect_list[i]["state"],
                            }
                        ), "{i} 番目の操作が期待値と異なります。".format(i=i)
                    else:
                        assert hist_list[i] == expect_list[i], "{i} 番目の操作が期待値と異なります。".format(i=i)


def app_log_check(
    client,
    expect_list,
    is_strict=True,
):
    import logging

    response = client.get("/rasp-water/api/log_view")

    log_list = response.json["data"]

    logging.debug(log_list)

    if is_strict:
        # NOTE: クリアする直前のログが残っている可能性があるので，+1 でも OK とする
        assert (len(log_list) == len(expect_list)) or (len(log_list) == (len(expect_list) + 1))

    for (i, expect) in enumerate(reversed(expect_list)):
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
            assert False, "テストコードのバグです．({expect})".format(expect=expect)


def ctrl_log_clear():
    import valve

    valve.GPIO.hist_clear()


def schedule_clear(client):
    schedule_data = gen_schedule_data()
    schedule_data[0]["is_active"] = False
    schedule_data[1]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200


def app_log_clear(client):
    response = client.get("/rasp-water/api/log_clear")
    assert response.status_code == 200


def check_notify_slack(message, index=-1):
    import logging

    import notify_slack

    notify_hist = notify_slack.hist_get()
    logging.debug(notify_hist)

    if message is None:
        assert notify_hist == [], "正常なはずなのに，エラー通知がされています。"
    else:
        assert len(notify_hist) != 0, "異常が発生したはずなのに，エラー通知がされていません。"
        assert notify_hist[index].find(message) != -1, "「{message}」が Slack で通知されていません。".format(
            message=message
        )


######################################################################
def test_time(freezer):
    import logging

    import schedule

    logging.debug(
        "datetime.now()                 = {date}".format(date=datetime.datetime.now()),
    )
    logging.debug("datetime.now(JST)              = {date}".format(date=datetime.datetime.now(TIMEZONE)))
    logging.debug(
        "datetime.now().replace(...)    = {date}".format(
            date=datetime.datetime.now().replace(hour=0, minute=0, second=0)
        )
    )
    logging.debug(
        "datetime.now(JST).replace(...) = {date}".format(
            date=datetime.datetime.now(TIMEZONE).replace(hour=0, minute=0, second=0)
        )
    )

    logging.debug("Freeze time at {time}".format(time=time_str(time_test(0))))
    move_to(freezer, time_test(0))

    logging.debug(
        "datetime.now()                 = {date}".format(date=datetime.datetime.now()),
    )
    logging.debug("datetime.now(JST)              = {date}".format(date=datetime.datetime.now(TIMEZONE)))

    schedule.clear()
    job_time_str = time_str(time_test(1))
    logging.debug("set schedule at {time}".format(time=job_time_str))
    job = schedule.every().day.at(job_time_str, TIMEZONE_PYTZ).do(lambda: True)

    idle_sec = schedule.idle_seconds()
    logging.error("Time to next jobs is {idle:.1f} sec".format(idle=idle_sec))
    logging.debug("Next run is {time}".format(time=job.next_run))

    assert abs(idle_sec - 60) < 5


def test_redirect(client):
    response = client.get("/")
    assert response.status_code == 302
    assert re.search(r"/rasp-water/$", response.location)
    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_index(client):
    response = client.get("/rasp-water/")
    assert response.status_code == 200
    assert "散水システム" in response.data.decode("utf-8")

    response = client.get("/rasp-water/", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_index_with_other_status(client, mocker):
    mocker.patch(
        "flask.wrappers.Response.status_code",
        return_value=301,
        new_callable=mocker.PropertyMock,
    )

    response = client.get("/rasp-water/", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 301
    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_valve_ctrl_read(client):
    response = client.get(
        "/rasp-water/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"
    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_valve_ctrl_read_fail(client, mocker):
    mocker.patch("valve.get_control_mode", side_effect=RuntimeError())

    response = client.get(
        "/rasp-water/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "fail"
    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_valve_ctrl_mismatch(client):
    import valve

    # NOTE: Fault injection
    valve.set_control_mode(-10)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"
    time.sleep(5)

    ctrl_log_check([{"state": "open"}, {"period": 0, "state": "close"}])
    # NOTE: 強引にバルブを開いているのでアプリのログには記録されない
    app_log_check(client, ["CLEAR", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_manual(client, mocker):
    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)
    # NOTE: ログ表示の際のエラーも仕込んでおく
    mocker.patch("socket.gethostbyaddr", side_effect=RuntimeError())

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    ctrl_log_check([{"state": "open"}, {"period": period, "state": "close"}], is_strict=False)
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto(client, mocker):
    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    ctrl_log_check([{"state": "open"}, {"period": period, "state": "close"}], is_strict=False)
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_rainfall(client, mocker):
    mocker.patch("weather_forecast.get_rain_fall", return_value=True)

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    # NOTE: ダミーモードの場合は，天気に関わらず水やりする
    ctrl_log_check([{"state": "open"}, {"period": period, "state": "close"}], is_strict=False)
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])

    ctrl_log_clear()
    app_log_clear(client)

    mocker.patch.dict(os.environ, {"DUMMY_MODE": "false"}, clear=True)
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    ctrl_log_check([])
    app_log_check(client, ["CLEAR", "PENDING"])
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast(client, mocker):
    mocker.patch("weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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
    mocker.patch("weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)
    mocker.patch("weather_forecast.get_weather_info_yahoo", return_value=None)

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    # NOTE: get_weather_info_yahoo == None の場合，水やりは行う
    ctrl_log_check([{"state": "open"}, {"period": period, "state": "close"}], is_strict=False)
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast_error_2(client, mocker):
    import weather_forecast

    mocker.patch("weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)

    response_mock = mocker.Mock()
    response_mock.status_code = 404
    mocker.patch.object(weather_forecast.requests, "get", retrun_value=response_mock)

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    ctrl_log_check([{"state": "open"}, {"period": period, "state": "close"}], is_strict=False)
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast_error_3(client, mocker):
    import requests

    mocker.patch("weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)

    response = requests.models.Response()
    response.status_code = 500
    mocker.patch("weather_forecast.requests.get", return_value=response)

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    ctrl_log_check([{"state": "open"}, {"period": period, "state": "close"}], is_strict=False)
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_ctrl_auto_forecast_error_4(client, mocker):
    import weather_forecast

    mocker.patch("weather_forecast.get_rain_fall", side_effect=get_rain_fall_orig)
    mocker.patch.object(weather_forecast.requests, "get", side_effect=RuntimeError())

    period = 2
    response = client.get(
        "/rasp-water/api/valve_ctrl",
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

    ctrl_log_check([{"state": "open"}, {"period": period, "state": "close"}], is_strict=False)
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_valve_flow(client):
    response = client.get("/rasp-water/api/valve_flow")
    assert response.status_code == 200
    assert "flow" in response.json

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 0,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    response = client.get("/rasp-water/api/valve_flow")
    assert response.status_code == 200
    assert "flow" in response.json

    time.sleep(1)

    ctrl_log_check([{"state": "close"}])
    app_log_check(client, ["CLEAR", "STOP_MANUAL"])
    check_notify_slack(None)


def test_event(client):
    response = client.get("/rasp-water/api/event", query_string={"count": "2"})
    assert response.status_code == 200
    assert response.data.decode()

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_inactive(client, freezer):
    move_to(freezer, time_test(0))
    time.sleep(0.6)

    schedule_data = gen_schedule_data()
    schedule_data[0]["is_active"] = False
    schedule_data[1]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    move_to(freezer, time_test(1))
    time.sleep(0.6)

    move_to(freezer, time_test(2))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(3)
    schedule_data[0]["wday"] = [False] * 7
    schedule_data[1]["wday"] = [False] * 7
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    move_to(freezer, time_test(3))
    time.sleep(0.6)

    move_to(freezer, time_test(4))
    time.sleep(0.6)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR", "SCHEDULE", "SCHEDULE"])
    check_notify_slack(None)


def test_schedule_ctrl_invalid(client, mocker):
    import notify_slack

    notify_slack.interval_clear()

    schedule_data = gen_schedule_data()
    del schedule_data[0]["period"]
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data.pop(0)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["is_active"] = "TEST"
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["time"] = "TEST"
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["period"] = "TEST"
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["wday"] = [True] * 5
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["wday"] = ["TEST"] * 7
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    time.sleep(4)

    ctrl_log_check([])
    app_log_check(
        client, ["CLEAR", "INVALID", "INVALID", "INVALID", "INVALID", "INVALID", "INVALID", "INVALID"]
    )
    check_notify_slack("スケジュールの指定が不正です。")


def test_valve_flow_open_over_1(client, mocker):
    flow_mock = mocker.patch("valve.get_flow")
    flow_mock.return_value = {"flow": 100, "result": "success"}

    mocker.patch("valve.TIME_OVER_FAIL", 0.5)
    # NOTE: これをやっておかないと，後続のテストに影響がでる
    mocker.patch("valve.TIME_ZERO_TAIL", 1)

    period = 3
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "open"}, {"period": period, "state": "close"}, {"state": "close"}],
        is_strict=False,
    )
    app_log_check(client, ["FAIL_OVER"], False)
    check_notify_slack("水が流れすぎています。")

    flow_mock.return_value = {"flow": 0, "result": "success"}
    time.sleep(1)


def test_valve_flow_open_over_2(client, mocker):
    flow_mock = mocker.patch("valve.get_flow")
    flow_mock.return_value = {"flow": 100, "result": "success"}

    mocker.patch("valve.TIME_CLOSE_FAIL", 1)
    # NOTE: これをやっておかないと，後続のテストに影響がでる
    mocker.patch("valve.TIME_ZERO_TAIL", 1)

    period = 3
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "open"}, {"period": period, "state": "close"}, {"state": "close"}],
        is_strict=False,
    )
    app_log_check(client, ["FAIL_OVER"], False)
    check_notify_slack("水が流れすぎています。")

    flow_mock.return_value = {"flow": 0, "result": "success"}
    time.sleep(1)


def test_valve_flow_close_fail(client, mocker):
    # NOTE: Fault injection
    flow_mock = mocker.patch("valve.get_flow")
    flow_mock.return_value = {"flow": 0.1, "result": "success"}
    mocker.patch("valve.TIME_OPEN_FAIL", 1)

    period = 3
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )

    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "open"}, {"period": period, "state": "close"}, {"state": "close"}],
        is_strict=False,
        is_error=True,
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "FAIL_CLOSE"])
    check_notify_slack("バルブを閉めても水が流れ続けています。")

    flow_mock.return_value = {"flow": 0, "result": "success"}
    time.sleep(1)


def test_valve_flow_open_fail(client, mocker):
    # NOTE: Fault injection
    flow_mock = mocker.patch("valve.get_flow")
    flow_mock.return_value = {"flow": 0, "result": "success"}
    mocker.patch("valve.TIME_CLOSE_FAIL", 1)
    mocker.patch("valve.TIME_ZERO_TAIL", 1)

    period = 3
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check(
        [{"state": "open"}, {"period": period, "state": "close"}],
        is_strict=False,
    )
    app_log_check(client, ["CLEAR", "START_AUTO", "STOP_AUTO", "FAIL_OPEN"])
    check_notify_slack("元栓が閉まっている可能性があります。")

    flow_mock.return_value = {"flow": 0, "result": "success"}
    time.sleep(1)


def test_valve_flow_read_command_fail(client, mocker):
    import builtins

    import valve

    orig_open = builtins.open

    def open_mock(
        file,
        mode="r",
        buffering=-1,
        encoding=None,
        errors=None,
        newline=None,
        closefd=True,
        opener=None,
    ):
        if (file == valve.STAT_PATH_VALVE_CONTROL_COMMAND) and (mode == "r"):
            return RuntimeError()
        else:
            return orig_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

    mocker.patch("valve.valve_open", side_effect=open_mock)

    period = 3
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": period,
        },
    )
    assert response.status_code == 200

    time.sleep(period + 5)

    ctrl_log_check([{"state": "open"}])
    app_log_check(client, ["CLEAR", "START_AUTO"])
    check_notify_slack(None)

    # NOTE: 後始末をしておく
    valve.STAT_PATH_VALVE_CONTROL_COMMAND.unlink(missing_ok=True)
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 0,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"


def test_schedule_ctrl_execute(client, mocker, freezer):
    import rasp_water_valve
    from config import load_config

    rasp_water_valve.term()

    time.sleep(1)

    time_mock = mocker.patch("valve.valve_time")

    move_to(freezer, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(1)

    rasp_water_valve.init(load_config(CONFIG_FILE))
    ctrl_log_clear()

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(1)

    move_to(freezer, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(freezer, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(20)

    move_to(freezer, time_test(3))
    time_mock.return_value = time.time()
    time.sleep(20)

    response = client.get("/rasp-water/api/valve_flow")
    assert response.status_code == 200
    assert "flow" in response.json

    # NOTE: 天気次第で結果が変わるのでログのチェックは行わない
    check_notify_slack(None)


def test_schedule_ctrl_execute_force(client, mocker, freezer):
    import rasp_water_valve
    from config import load_config

    # NOTE: 一旦初期化を終わらせてから、胡椒注入のために rasp_water_valve を止める
    time.sleep(3)
    rasp_water_valve.term()

    time.sleep(1)

    mocker.patch("rasp_water_valve.judge_execute", return_value=True)
    time_mock = mocker.patch("valve.valve_time")

    move_to(freezer, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(1)

    rasp_water_valve.init(load_config(CONFIG_FILE))
    ctrl_log_clear()

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(1)

    move_to(freezer, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(freezer, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(20)

    move_to(freezer, time_test(3))
    time_mock.return_value = time.time()
    time.sleep(20)

    ctrl_log_check([{"state": "open"}, {"state": "close", "period": 60}])
    app_log_check(client, ["CLEAR", "SCHEDULE", "START_AUTO", "STOP_AUTO"])
    check_notify_slack(None)


def test_schedule_ctrl_execute_pending(client, mocker, freezer):
    import rasp_water_valve
    from config import load_config

    rasp_water_valve.term()

    time.sleep(1)

    mocker.patch("rasp_water_valve.judge_execute", return_value=False)
    time_mock = mocker.patch("valve.valve_time")

    move_to(freezer, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(1)

    rasp_water_valve.init(load_config(CONFIG_FILE))
    ctrl_log_clear()

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(1)

    move_to(freezer, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(freezer, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(20)

    move_to(freezer, time_test(3))
    time_mock.return_value = time.time()
    time.sleep(20)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR", "SCHEDULE"])
    check_notify_slack(None)


def test_schedule_ctrl_error(client, mocker, freezer):
    import rasp_water_valve
    from config import load_config

    valve_state_moch = mocker.patch("rasp_water_valve.set_valve_state")
    valve_state_moch.side_effect = RuntimeError()

    rasp_water_valve.term()

    time_mock = mocker.patch("valve.valve_time")

    time.sleep(3)

    move_to(freezer, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(0.6)

    rasp_water_valve.init(load_config(CONFIG_FILE))
    ctrl_log_clear()

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    move_to(freezer, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(freezer, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(4)

    move_to(freezer, time_test(3))
    time_mock.return_value = time.time()
    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR", "SCHEDULE", "FAIL_AUTO"])
    check_notify_slack(None)


def test_schedule_ctrl_execute_fail(client, mocker, freezer):
    import rasp_water_valve
    from config import load_config

    mocker.patch("weather_forecast.get_rain_fall", return_value=False)
    mocker.patch("app_scheduler.valve_auto_control_impl", return_value=False)

    rasp_water_valve.term()

    time_mock = mocker.patch("valve.valve_time")

    time.sleep(3)

    move_to(freezer, time_test(0))
    time_mock.return_value = time.time()
    time.sleep(0.6)

    rasp_water_valve.init(load_config(CONFIG_FILE))
    ctrl_log_clear()

    schedule_data = gen_schedule_data()
    schedule_data[1]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    move_to(freezer, time_test(1))
    time_mock.return_value = time.time()
    time.sleep(2)

    move_to(freezer, time_test(2))
    time_mock.return_value = time.time()
    time.sleep(4)

    move_to(freezer, time_test(3))
    time_mock.return_value = time.time()
    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR", "SCHEDULE", "FAIL_AUTO"])
    check_notify_slack(None)


def test_schedule_ctrl_read(client):
    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_read_fail_1(client):
    import webapp_config

    with open(webapp_config.SCHEDULE_DATA_PATH, "wb") as f:
        f.write(b"TEST")

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR", "FAIL_READ"])
    check_notify_slack("スケジュール設定の読み出しに失敗しました。")


def test_schedule_ctrl_read_fail_2(client):
    import webapp_config

    webapp_config.SCHEDULE_DATA_PATH.unlink(missing_ok=True)

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_read_fail_3(client, mocker):
    pickle_mock = mocker.patch("pickle.load")

    schedule_data = gen_schedule_data()
    schedule_data.pop(0)
    pickle_mock.return_value = schedule_data

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    schedule_data = gen_schedule_data()
    pickle_mock.return_value = schedule_data

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_schedule_ctrl_write_fail(client, mocker):
    from pickle import dump as dump_orig

    mocker.patch("pickle.dump", side_effect=RuntimeError())

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    mocker.patch("pickle.dump", side_effect=dump_orig)

    # NOTE: 次回のテストに向けて，正常なものに戻しておく
    schedule_data = gen_schedule_data()
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(2)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR", "FAIL_WRITE", "SCHEDULE", "FAIL_READ", "SCHEDULE"], False)
    check_notify_slack("スケジュール設定の保存に失敗しました。", 0)


def test_schedule_ctrl_validate_fail(client, mocker):
    mocker.patch("app_scheduler.schedule_validate", return_value=False)

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_log_view(client):
    response = client.get(
        "/rasp-water/api/log_view",
        headers={"Accept-Encoding": "gzip"},
        query_string={
            "callback": "TEST",
        },
    )
    assert response.status_code == 200

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_log_clear(client):
    response = client.get("/rasp-water/api/log_clear")
    assert response.status_code == 200

    response = client.get(
        "/rasp-water/api/log_view",
        headers={"Accept-Encoding": "gzip"},
        query_string={
            "callback": "TEST",
        },
    )
    assert response.status_code == 200

    time.sleep(1)

    ctrl_log_check([])
    app_log_check(client, ["CLEAR"])
    check_notify_slack(None)


def test_sysinfo(client):
    response = client.get("/rasp-water/api/sysinfo")
    assert response.status_code == 200
    assert "date" in response.json
    assert "uptime" in response.json
    assert "loadAverage" in response.json


def test_snapshot(client):
    response = client.get("/rasp-water/api/snapshot")
    assert response.status_code == 200
    assert "msg" in response.json
    response = client.get("/rasp-water/api/snapshot")
    assert response.status_code == 200
    assert "msg" not in response.json


def test_memory(client):
    response = client.get("/rasp-water/api/memory")
    assert response.status_code == 200
    assert "memory" in response.json


def test_second_str():
    import rasp_water_valve

    assert rasp_water_valve.second_str(60) == "1分"
    assert rasp_water_valve.second_str(61) == "1分1秒"


def test_valve_init(client, mocker):
    import builtins

    import rasp_water_valve
    import valve
    from config import load_config

    rasp_water_valve.term()
    time.sleep(2)

    mocker.patch("pathlib.Path.exists", return_value=True)
    file_mock = mocker.MagicMock()
    file_mock.write.return_value = True
    orig_open = builtins.open

    def open_mock(
        file,
        mode="r",
        buffering=-1,
        encoding=None,
        errors=None,
        newline=None,
        closefd=True,
        opener=None,
    ):
        if file == valve.ADC_SCALE_PATH:
            return file_mock
        else:
            return orig_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

    mocker.patch("builtins.open", side_effect=open_mock)

    rasp_water_valve.init(load_config(CONFIG_FILE))


def test_terminate():
    import rasp_water_schedule
    import rasp_water_valve
    import webapp_log

    webapp_log.term()
    rasp_water_schedule.term()
    rasp_water_valve.term()

    # NOTE: 二重に呼んでもエラーにならないことを確認
    webapp_log.term()
    rasp_water_schedule.term()
    rasp_water_valve.term()
