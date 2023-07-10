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


@pytest.fixture(scope="session")
def app():
    import webapp_config

    webapp_config.SCHEDULE_DATA_PATH.unlink(missing_ok=True)

    os.environ["TEST"] = "true"
    os.environ["WERKZEUG_RUN_MAIN"] = "true"

    app = create_app("config.yaml", dummy_mode=True)

    yield app


@pytest.fixture()
def client(app):

    test_client = app.test_client()

    yield test_client

    test_client.delete()


def time_str_after(min):
    return (datetime.datetime.now() + datetime.timedelta(minutes=min)).strftime("%H:%M")


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


def test_valve_ctrl_read(client, mocker):
    response = client.get(
        "/rasp-water/api/valve_ctrl",
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"


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

    period = 15
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
            "period": 2,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"

    mocker.patch("weather_forecast.get_weather_info_yahoo", return_value=None)

    response = client.get(
        "/rasp-water/api/valve_ctrl",
        query_string={
            "cmd": 1,
            "state": 1,
            "auto": 1,
            "period": 2,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"


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
    mocker.patch("slack_sdk.WebClient.chat_postMessage", return_value=True)

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


def test_schedule_ctrl_execute(client):
    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(120)


def test_schedule_ctrl_execute_pending(client, mocker):
    mocker.patch("weather_forecast.get_rain_fall", return_value=True)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(120)


def test_schedule_ctrl_execute_fail(client, mocker):
    mocker.patch("weather_forecast.get_rain_fall", return_value=False)
    mocker.patch("scheduler.valve_auto_control_impl", return_value=False)

    schedule_data = gen_schedule_data(1)
    response = client.get(
        "/rasp-water/api/schedule_ctrl",
        query_string={"cmd": "set", "data": json.dumps(schedule_data)},
    )
    assert response.status_code == 200
    time.sleep(62)


def test_schedule_ctrl_read(client):
    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2


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
    from functools import partial
    import valve
    import notify_slack

    notify_slack.clear_interval()

    mocker.patch("slack_sdk.WebClient.chat_postMessage", return_value=True)
    # NOTE: Fault injection
    mocker.patch("valve.get_flow", partial(valve.get_flow, valve.FAIL_MODE.OPEN))
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


def test_valve_flow_close(client, mocker):
    from functools import partial
    import valve
    import notify_slack

    notify_slack.clear_interval()

    mocker.patch("slack_sdk.WebClient.chat_postMessage", return_value=True)
    # NOTE: Fault injection
    mocker.patch("valve.get_flow", partial(valve.get_flow, valve.FAIL_MODE.CLOSE))
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
