#!/usr/bin/env python3
"""
雨量データを取得します．

Usage:
  weather_sensor.py [-c CONFIG] [-d DAYS]

Options:
  -c CONFIG    : CONFIG を設定ファイルとして読み込んで実行します．[default: config.yaml]
  -d DAYS      : 集計する日数を指定します．[default: 1]
"""

import datetime
import logging

import rasp_water.scheduler
from my_lib.sensor_data import get_day_sum


def days_since_last_watering():
    schedule_data = rasp_water.scheduler.schedule_load()

    wday_list = [x or y for x, y in zip(schedule_data[0]["wday"], schedule_data[1]["wday"])]
    wday = datetime.datetime.now().weekday()  # noqa: DTZ005

    for i in range(1, len(wday_list) + 1):
        index = (wday - i) % len(wday_list)
        if wday_list[index]:
            return i
    return 7


def get_rain_fall_sum(config, days):
    return get_day_sum(
        config["influxdb"],
        config["weather"]["rain_fall"]["sensor"]["type"],
        config["weather"]["rain_fall"]["sensor"]["name"],
        "rain",
        days=days,
    )


def get_rain_fall(config):
    days = days_since_last_watering()
    rain_fall_sum = get_rain_fall_sum(config, days)

    logging.info("Rain fall sum since last watering: %.1f (%d days)", rain_fall_sum, days)

    rainfall_judge = rain_fall_sum > config["weather"]["rain_fall"]["sensor"]["threshold"]["sum"]
    logging.info("Rain fall sensor judge: %s", rainfall_judge)

    return rainfall_judge


if __name__ == "__main__":
    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.webapp.config

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    days = int(args["-d"])

    my_lib.logger.init("test", level=logging.INFO)

    config = my_lib.config.load(config_file)

    my_lib.webapp.config.init(config)
    rasp_water.scheduler.init()

    logging.info("Sum of rainfall is %.1f", get_rain_fall_sum(config, days))

    logging.info("Finish.")
