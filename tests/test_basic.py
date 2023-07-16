#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import pathlib
import pytest
import re
import time
import json
import datetime

sys.path.append(str(pathlib.Path(__file__).parent.parent / "flask" / "app"))

from app import create_app

CONFIG_FILE = "config.example.yaml"


@pytest.fixture(scope="session")
def app():
    os.environ["TEST"] = "true"
    os.environ["WERKZEUG_RUN_MAIN"] = "true"

    app = create_app(CONFIG_FILE, dummy_mode=True)

    yield app

    # NOTE: 特定のテストのみ実行したときのため，ここでも呼ぶ
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
        "notify_slack.slack_sdk.web.client.WebClient.chat_postMessage",
        side_effect=slack_sdk.errors.SlackClientError(),
    )

    test_client = app.test_client()

    yield test_client

    test_client.delete()


def time_after(min):
    return datetime.datetime.now() + datetime.timedelta(minutes=min)


def time_str_after(min):
    return time_after(min).strftime("%H:%M")


def gen_schedule_data(min=10):
    return [
        {
            "is_active": True,
            "time": time_str_after(min),
            "period": 1,
            "wday": [True] * 7,
        }
    ] * 2


def test_redirect(client):
    response = client.get("/")
    assert response.status_code == 302
    assert re.search(r"/rasp-water/$", response.location)


def test_index(client):
    response = client.get("/rasp-water/")
    assert response.status_code == 200
    assert "散水システム" in response.data.decode("utf-8")

    response = client.get("/rasp-water/", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200


def test_index_with_other_status(client, mocker):
    mocker.patch(
        "flask.wrappers.Response.status_code",
        return_value=301,
        new_callable=mocker.PropertyMock,
    )

    response = client.get("/rasp-water/", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 301


def test_valve_ctrl_read(client):
    response = client.get(
        "/rasp-water/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"


def test_valve_ctrl_read_fail(client, mocker):
    mocker.patch("valve.get_control_mode", side_effect=RuntimeError())

    response = client.get(
        "/rasp-water/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "fail"


def test_valve_ctrl_mismatch(client):
    import valve

    # NOTE: Fault injection
    valve.set_control_mode(-10)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"


def test_valve_ctrl_manual(client, mocker):
    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)
    # NOTE: ログ表示の際のエラーも仕込んでおく
    mocker.patch("socket.gethostbyaddr", side_effect=RuntimeError())

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
    assert response.json["result"] == "success"
    assert response.json["remain"] > (period - 2)

    time.sleep(period)


def test_valve_ctrl_auto(client, mocker):
    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    # NOTE: 下記の時間を削るとこのテストが終わらないうちに次のテストが
    # 始まってしまうので，削除しないこと．
    time.sleep(2)


def test_valve_ctrl_auto_forecast_error_1(client, mocker):
    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)

    mocker.patch("weather_forecast.get_weather_info_yahoo", return_value=None)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(2)


def test_valve_ctrl_auto_forecast_error_2(client, mocker):
    import weather_forecast

    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)

    response_mock = mocker.Mock()
    response_mock.status_code = 404
    mocker.patch.object(weather_forecast.requests, "get", retrun_value=response_mock)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(2)


def test_valve_ctrl_auto_forecast_error_3(client, mocker):
    import weather_forecast

    mocker.patch("fluent.sender.FluentSender.emit", return_value=True)

    response_mock = mocker.Mock()
    response_mock.status_code = 404
    mocker.patch.object(weather_forecast.requests, "get", side_effect=RuntimeError())

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    time.sleep(2)


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


def test_event(client):
    response = client.get("/rasp-water/api/event", query_string={"count": "2"})
    assert response.status_code == 200
    assert response.data.decode()


def test_schedule_ctrl_inactive(client):
    schedule_data = gen_schedule_data()
    schedule_data[0]["is_active"] = False
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    schedule_data = gen_schedule_data()
    schedule_data[0]["wday"] = [False] * 7
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200


def test_schedule_ctrl_invalid(client, mocker):
    import notify_slack

    notify_slack.clear_interval()

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

    time.sleep(2)


def test_schedule_ctrl_execute(client, freezer):
    freezer.move_to(time_after(0))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    freezer.move_to(time_after(2))
    time.sleep(0.6)


def test_schedule_ctrl_execute_force(client, mocker, freezer):
    mocker.patch("rasp_water_valve.judge_execute", return_value=True)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    freezer.move_to(time_after(2))
    time.sleep(0.6)


def test_schedule_ctrl_execute_pending_1(client, mocker, freezer):
    mocker.patch("weather_forecast.get_rain_fall", return_value=True)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    freezer.move_to(time_after(2))
    time.sleep(0.6)


def test_schedule_ctrl_execute_pending_2(client, mocker, freezer):
    mocker.patch("rasp_water_valve.judge_execute", return_value=False)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    freezer.move_to(time_after(2))
    time.sleep(0.6)


def test_schedule_ctrl_error(client, mocker, freezer):
    mocker.patch("rasp_water_valve.judge_execute", return_value=True)
    valve_state_moch = mocker.patch("rasp_water_valve.set_valve_state")

    valve_state_moch.side_effect = RuntimeError()

    freezer.move_to(time_after(0))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    valve_state_moch.return_value = True

    schedule_data = gen_schedule_data(2)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    freezer.move_to(time_after(2))
    time.sleep(0.6)

    freezer.move_to(time_after(3))
    time.sleep(0.6)


def test_schedule_ctrl_execute_fail(client, mocker, freezer):
    mocker.patch("weather_forecast.get_rain_fall", return_value=False)
    mocker.patch("scheduler.valve_auto_control_impl", return_value=False)

    freezer.move_to(time_after(0))
    time.sleep(0.6)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(0.6)

    freezer.move_to(time_after(1))
    time.sleep(0.6)

    freezer.move_to(time_after(2))
    time.sleep(0.6)


def test_schedule_ctrl_read(client):
    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2


def test_schedule_ctrl_read_fail_1(client):
    import webapp_config

    with open(webapp_config.SCHEDULE_DATA_PATH, "wb") as f:
        f.write(b"TEST")

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2


def test_schedule_ctrl_read_fail_2(client):
    import webapp_config

    webapp_config.SCHEDULE_DATA_PATH.unlink(missing_ok=True)

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2


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


def test_schedule_ctrl_write_fail(client, mocker):
    mocker.patch("pickle.dump", side_effect=RuntimeError())

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200

    # NOTE: 次回のテストに向けて，正常なものに戻しておく
    schedule_data = gen_schedule_data()
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(1)


def test_schedule_ctrl_validate_fail(client, mocker):
    mocker.patch("scheduler.schedule_validate", return_value=False)

    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2


def test_log_view(client):
    response = client.get(
        "/rasp-water/api/log_view",
        headers={"Accept-Encoding": "gzip"},
        query_string={
            "callback": "TEST",
        },
    )
    assert response.status_code == 200


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


def test_sysinfo(client):
    response = client.get("/rasp-water/api/sysinfo")
    assert response.status_code == 200


def test_snapshot(client):
    response = client.get("/rasp-water/api/snapshot")
    assert response.status_code == 200
    response = client.get("/rasp-water/api/snapshot")
    assert response.status_code == 200


def test_memory(client):
    response = client.get("/rasp-water/api/memory")
    assert response.status_code == 200


def test_valve_flow_open(client, mocker):
    import notify_slack

    notify_slack.clear_interval()

    # NOTE: Fault injection
    mocker.patch("valve.get_flow", return_value={"flow": 10, "result": "success"})
    mocker.patch("valve.TIME_OPEN_FAIL", 1)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200

    time.sleep(10)


def test_valve_flow_open_over(client, mocker):
    import notify_slack

    notify_slack.clear_interval()

    flow_mock = mocker.patch("valve.get_flow")
    mocker.patch("valve.TIME_OVER_FAIL", 1)

    flow_mock.return_value = {"flow": 100, "result": "success"}
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": 2,
        },
    )
    assert response.status_code == 200

    time.sleep(4)


def test_valve_flow_close_ok(client, mocker):
    import notify_slack

    notify_slack.clear_interval()

    flow_mock = mocker.patch("valve.get_flow")
    mocker.patch("valve.TIME_CLOSE_FAIL", 1)

    flow_mock.return_value = {"flow": 100, "result": "success"}
    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200

    time.sleep(2)

    flow_mock.return_value = {"flow": 0, "result": "success"}

    time.sleep(6)


def test_valve_flow_close_fail(client, mocker):
    import notify_slack

    notify_slack.clear_interval()

    # NOTE: Fault injection
    mocker.patch("valve.get_flow", return_value={"flow": 0, "result": "success"})
    mocker.patch("valve.TIME_CLOSE_FAIL", 1)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200

    time.sleep(15)


def test_second_str():
    import rasp_water_valve

    assert rasp_water_valve.second_str(60) == "1分"
    assert rasp_water_valve.second_str(61) == "1分1秒"


def test_valve_init(client, mocker):
    import builtins
    from config import load_config
    import rasp_water_valve
    import valve

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
            return orig_open(
                file, mode, buffering, encoding, errors, newline, closefd, opener
            )

    mocker.patch("builtins.open", side_effect=open_mock)

    rasp_water_valve.init(load_config(CONFIG_FILE))


def test_terminate():
    import webapp_log
    import rasp_water_schedule
    import rasp_water_valve

    webapp_log.term()
    rasp_water_schedule.term()
    rasp_water_valve.term()

    # NOTE: 二重に呼んでもエラーにならないことを確認
    webapp_log.term()
    rasp_water_schedule.term()
    rasp_water_valve.term()
