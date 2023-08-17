#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pathlib
import random
import sys
import time

# from flaky import flaky
from playwright.sync_api import expect

sys.path.append(str(pathlib.Path(__file__).parent.parent / "flask" / "lib"))

from webapp_config import TIMEZONE, TIMEZONE_OFFSET, TIMEZONE_PYTZ

APP_URL_TMPL = "http://{host}:{port}/rasp-water/"

SCHEDULE_AFTER_MIN = 1
PERIOD_MIN = 1


def check_log(page, message, timeout_sec=3):
    expect(page.locator("//app-log//div").first).to_contain_text(message, timeout=timeout_sec * 1000)

    # NOTE: ログクリアする場合，ログの内容が変化しているので，ここで再取得する
    log_list = page.locator("//app-log//div")
    for i in range(log_list.count()):
        expect(log_list.nth(i)).not_to_contain_text("失敗")
        expect(log_list.nth(i)).not_to_contain_text("エラー")


def time_str_random():
    return "{hour:02d}:{min:02d}".format(hour=int(24 * random.random()), min=int(60 * random.random()))


def time_str_after(min):
    return (datetime.datetime.now(TIMEZONE) + datetime.timedelta(minutes=min)).strftime("%H:%M")


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
def test_time(freezer):
    import logging

    import schedule

    logging.error(
        "datetime.now()                 = {date}".format(date=datetime.datetime.now()),
    )
    logging.error("datetime.now(JST)              = {date}".format(date=datetime.datetime.now(TIMEZONE)))
    logging.error(
        "datetime.now().replace(...)    = {date}".format(
            date=datetime.datetime.now().replace(hour=0, minute=0, second=0)
        )
    )
    logging.error(
        "datetime.now(JST).replace(...) = {date}".format(
            date=datetime.datetime.now(TIMEZONE).replace(hour=0, minute=0, second=0)
        )
    )

    schedule.clear()
    job_time_str = time_str_after(SCHEDULE_AFTER_MIN)
    logging.error("set schedule at {time}".format(time=job_time_str))
    job = schedule.every().day.at(job_time_str, TIMEZONE_PYTZ).do(lambda: True)

    idle_sec = schedule.idle_seconds()
    logging.error(
        "Time to next jobs is {idle:.1f} sec ({idle_corrected:.1f} sec)".format(
            idle=idle_sec, idle_corrected=idle_sec - int(TIMEZONE_OFFSET) * 60 * 60
        )
    )
    logging.error("Next run is {time}".format(time=job.next_run))

    assert abs(idle_sec - int(TIMEZONE_OFFSET) * 60 * 60) < 60


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


def test_schedule_run(page, host, port):
    init(page)
    page.goto(app_url(host, port))

    page.locator('button:text("クリア")').click()
    time.sleep(1)
    check_log(page, "ログがクリアされました")

    # NOTE: 次の分で実行させるにあたって，秒数を調整する
    time.sleep((90 - datetime.datetime.now(TIMEZONE).second) % 60)

    enable_checkbox = page.locator('//input[contains(@id,"schedule-entry-")]')
    enable_wday_index = [bool_random() for _ in range(14)]
    wday_checkbox = page.locator('//input[@name="wday"]')
    time_input = page.locator('//input[@type="time"]')
    period_input = page.locator('//input[contains(@id,"schedule-period-")]')
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

        # NOTE: 散水時間は 1 分にする
        period_input.nth(i).fill(str(PERIOD_MIN))

    page.locator('button:text("保存")').click()

    check_log(page, "スケジュールを更新")

    check_log(page, "水やりを開始します", (SCHEDULE_AFTER_MIN * 60) + 10)

    check_log(page, "水やりを行いました", (PERIOD_MIN * 60) + 30)


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
    period_input = page.locator('//input[contains(@id,"schedule-period-")]')
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

        # NOTE: 散水時間は 1 分にする
        period_input.nth(i).fill(str(PERIOD_MIN))

        # NOTE: 無効にする
        enable_checkbox.nth(i).evaluate("node => node.click()")

    page.locator('button:text("保存")').click()

    check_log(page, "スケジュールを更新")

    # NOET: 何も実行されていないことを確認
    time.sleep((SCHEDULE_AFTER_MIN * 60) + 30)
    check_log(page, "スケジュールを更新")
