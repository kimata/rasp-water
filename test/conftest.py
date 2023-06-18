#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pytest


def pytest_addoption(parser):
    parser.addoption("--server", default="127.0.0.1")
    parser.addoption("--port", default="5000")


@pytest.fixture
def server(request):
    return request.config.getoption("--server")


@pytest.fixture
def port(request):
    return request.config.getoption("--port")
