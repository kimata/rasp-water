#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import random
import time

from flaky import flaky
from playwright.sync_api import expect

APP_URL_TMPL = "http://{host}:{port}/rasp-water/"


def check_log(page, message, timeout_sec=2):
    expect(page.locator("//app-log//div").first).to_contain_text(message, timeout=timeout_sec * 1000)

    # NOTE: ログクリアする場合，ログの内容が変化しているので，ここで再取得する
    log_list = page.locator("//app-log//div")
    for i in range(log_list.count()):
        expect(log_list.nth(i)).not_to_contain_text("失敗")
        expect(log_list.nth(i)).not_to_contain_text("エラー")


def time_str_random():
    return "{hour:02d}:{min:02d}".format(hour=int(24 * random.random()), min=int(60 * random.random()))


def time_str_after(min):
    return (datetime.datetime.now() + datetime.timedelta(minutes=min)).strftime("%H:%M")


def bool_random():
    return random.random() >= 0.5


def check_schedule(page, enable_schedule_index, schedule_time, enable_wday_index):
    enable_checkbox = page.locator('//input[contains(@id,"schedule-entry-")]')
    wday_checkbox = page.locator('//input[@name="wday"]')
    time_input = page.locator('//input[@type="time"]')

    for i in range(enable_checkbox.count()):
        if i == enable_schedule_index:
            expect(enable_checkbox.nth(i)).to_be_checked()
        else:
            expect(enable_checkbox.nth(i)).not_to_be_checked()

        expect(time_input.nth(i)).to_have_value(schedule_time[i])
        for j in range(7):
            if enable_wday_index[i * 7 + j]:
                if enable_wday_index[i * 7 + j]:
                    expect(wday_checkbox.nth(i * 7 + j)).to_be_checked()
                else:
                    expect(wday_checkbox.nth(i * 7 + j)).not_to_be_checked()


def app_url(server, port):
    return APP_URL_TMPL.format(host=server, port=port)


def init(page):
    page.on("console", lambda msg: print(msg.text))
    page.set_viewport_size({"width": 2400, "height": 1600})


######################################################################
@flaky(max_runs=3)
def test_valve(page, host, port):
    init(page)
    page.goto(app_url(host, port))

    page.locator('button:text("クリア")').click()
    time.sleep(1)
    check_log(page, "ログがクリアされました")

    period = int(page.locator('//input[@id="momentaryPeriod"]').input_value())

    # NOTE: checkbox 自体は hidden にして，CSS で表示しているので，
    # 通常の locator では操作できない
    page.locator('//input[@id="valveSwitch"]').evaluate("node => node.click()")

    check_log(page, "水やりを開始します")
    check_log(page, "水やりを行いました", period * 60 + 10)


@flaky(max_runs=3)
def test_schedule(page, host, port):
    init(page)
    page.goto(app_url(host, port))

    page.locator('button:text("クリア")').click()
    time.sleep(1)
    check_log(page, "ログがクリアされました")

    # NOTE: ランダムなスケジュール設定を準備
    schedule_time = [time_str_random(), time_str_random()]
    enable_schedule_index = int(2 * random.random())
    enable_wday_index = [bool_random() for _ in range(14)]

    enable_checkbox = page.locator('//input[contains(@id,"schedule-entry-")]')
    wday_checkbox = page.locator('//input[@name="wday"]')
    time_input = page.locator('//input[@type="time"]')
    for i in range(enable_checkbox.count()):
        # NTE: 最初に強制的に有効にしておく
        enable_checkbox.nth(i).evaluate("node => node.checked = false")
        enable_checkbox.nth(i).evaluate("node => node.click()")

        time_input.nth(i).fill(schedule_time[i])

        for j in range(7):
            if enable_wday_index[i * 7 + j]:
                wday_checkbox.nth(i * 7 + j).check()
            else:
                wday_checkbox.nth(i * 7 + j).uncheck()

        if i != enable_schedule_index:
            enable_checkbox.nth(i).evaluate("node => node.click()")

    page.locator('button:text("保存")').click()
    check_log(page, "スケジュールを更新")

    check_schedule(page, enable_schedule_index, schedule_time, enable_wday_index)

    page.reload()

    check_schedule(page, enable_schedule_index, schedule_time, enable_wday_index)


@flaky(max_runs=3)
def test_schedule_run(page, host, port):
    SCHEDULE_AFTER_MIN = 1

    init(page)
    page.goto(app_url(host, port))

    page.locator('button:text("クリア")').click()
    time.sleep(1)
    check_log(page, "ログがクリアされました")

    enable_checkbox = page.locator('//input[contains(@id,"schedule-entry-")]')
    enable_wday_index = [bool_random() for _ in range(14)]
    wday_checkbox = page.locator('//input[@name="wday"]')
    time_input = page.locator('//input[@type="time"]')
    for i in range(enable_checkbox.count()):
        # NOTE: checkbox 自体は hidden にして，CSS で表示しているので，
        # 通常の locator では操作できない
        enable_checkbox.nth(i).evaluate("node => node.checked = false")
        enable_checkbox.nth(i).evaluate("node => node.click()")

        # NOTE: 曜日は全てチェック
        for j in range(7):
            if enable_wday_index[i * 7 + j]:
                wday_checkbox.nth(i * 7 + j).check()

        # NOTE: 片方はランダム，他方はテスト用に 1 分後に設定
        if i == 0:
            time_input.nth(i).fill(time_str_random())
        else:
            time_input.nth(i).fill(time_str_after(SCHEDULE_AFTER_MIN))

    period_input = page.locator('//input[contains(@id,"schedule-period-")]')
    period = int(period_input.nth(1).input_value())

    page.locator('button:text("保存")').click()

    check_log(page, "スケジュールを更新")

    check_log(page, "水やりを開始します", SCHEDULE_AFTER_MIN * 60 + 10)

    check_log(page, "水やりを行いました", period * 60 + 10)


@flaky(max_runs=3)
def test_schedule_disable(page, host, port):
    init(page)
    page.goto(app_url(host, port))

    page.locator('button:text("クリア")').click()
    time.sleep(1)
    check_log(page, "ログがクリアされました")

    enable_checkbox = page.locator('//input[contains(@id,"schedule-entry-")]')
    enable_wday_index = [bool_random() for _ in range(14)]
    wday_checkbox = page.locator('//input[@name="wday"]')
    time_input = page.locator('//input[@type="time"]')
    for i in range(enable_checkbox.count()):
        # NOTE: checkbox 自体は hidden にして，CSS で表示しているので，
        # 通常の locator では操作できない
        enable_checkbox.nth(i).evaluate("node => node.checked = false")
        enable_checkbox.nth(i).evaluate("node => node.click()")

        # NOTE: 曜日は全てチェック
        for j in range(7):
            if enable_wday_index[i * 7 + j]:
                wday_checkbox.nth(i * 7 + j).check()

        # NOET: 1分後にスケジュール設定
        time_input.nth(i).fill(time_str_after(i))

    page.locator('button:text("保存")').click()

    check_log(page, "スケジュールを更新")

    # NOET: 何も実行されていないことを確認
    time.sleep(60)
    check_log(page, "スケジュールを更新")
