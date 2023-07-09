#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import pathlib
import pytest
import re

sys.path.append(str(pathlib.Path(__file__).parent.parent / "flask" / "app"))

from app import create_app


@pytest.fixture()
def app():
    app = create_app("config.yaml", debug_mode=True, dummy_mode=True)
    yield app


@pytest.fixture
def client(app):
    os.environ["WERKZEUG_RUN_MAIN"] = "true"

    test_client = app.test_client()
    yield test_client
    test_client.delete()

    import webapp_log
    import rasp_water_schedule
    import rasp_water_valve

    webapp_log.term()
    rasp_water_schedule.term()
    rasp_water_valve.term()


def test_redirect(client):
    response = client.get("/")
    assert response.status_code == 302
    assert re.search(r"/rasp-water/$", response.location)


def test_index(client):
    response = client.get("/rasp-water/")
    assert response.status_code == 200
    assert "散水システム" in response.data.decode("utf-8")


def test_valve_ctrl(client):
    response = client.post(
        "/rasp-water/api/valve_ctrl",
        data={
            "cmd": 1,
            "state": 1,
            "period": 1,
        },
    )
    assert response.status_code == 200
    assert response.json["result"] == "success"


def test_valve_flow(client):
    response = client.get("/rasp-water/api/valve_flow")
    assert response.status_code == 200
    assert "flow" in response.json


def test_schedule_ctrl(client):
    response = client.get("/rasp-water/api/schedule_ctrl")
    assert response.status_code == 200
    assert len(response.json) == 2
