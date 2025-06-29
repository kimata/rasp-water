#!/usr/bin/env python3

import os
import pytest


def pytest_addoption(parser):
    parser.addoption("--host", default="127.0.0.1")
    parser.addoption("--port", default="5000")


@pytest.fixture
def host(request):
    return request.config.getoption("--host")


@pytest.fixture
def port(request):
    return int(request.config.getoption("--port"))


@pytest.fixture
def page(page):
    from playwright.sync_api import expect

    timeout = 10000  # 10秒に増やす
    page.set_default_navigation_timeout(timeout)
    page.set_default_timeout(timeout)
    expect.set_options(timeout=timeout)

    return page


@pytest.fixture
def browser_context_args(browser_context_args, request):
    return {
        **browser_context_args,
        "record_video_dir": f"tests/evidence/{request.node.name}",
        "record_video_size": {"width": 2400, "height": 1600},
    }


# Playwright設定をヘッドレスモードに強制（CIやX Serverなし環境向け）
@pytest.fixture(scope="session")
def browser_type_launch_args():
    return {
        "headless": True,  # 常にヘッドレスモードで実行
    }