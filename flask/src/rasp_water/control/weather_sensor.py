#!/usr/bin/env python3
"""
雨量データを取得します。

Usage:
  weather_sensor.py [-c CONFIG] [-p HOURS] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -p HOURS          : 集計する時間を指定します。[default: 12]
  -D                : デバッグモードで動作します。
"""

import datetime
import logging

import my_lib.sensor_data
import my_lib.time
import rasp_water.control.scheduler


def hours_since_last_watering():
    schedule_data = rasp_water.control.scheduler.schedule_load()

    now = my_lib.time.now()

    last_date = []
    for schedule in schedule_data:
        if not schedule["is_active"]:
            continue
        time_str = schedule["time"]
        hour, minute = map(int, time_str.split(":"))

        for days_ago in range(7):
            day = now - datetime.timedelta(days=days_ago)
            wday_index = day.weekday()
            if schedule["wday"][wday_index]:
                scheduled_date = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                last_date.append(scheduled_date)
                break

    if len(last_date) == 0:
        return 24 * 7

    minutes = (now - max(last_date)).total_seconds() / 60

    hours = int(minutes // 60)
    if minutes % 60 >= 30:
        hours += 1

    return hours


def get_rain_fall_sum(config, hours):
    return my_lib.sensor_data.get_hour_sum(
        config["influxdb"],
        config["weather"]["rain_fall"]["sensor"]["measure"],
        config["weather"]["rain_fall"]["sensor"]["hostname"],
        "rain",
        hours=hours,
    )


def get_rain_fall(config):
    hours = hours_since_last_watering()
    # InfluxDBクエリエラーを避けるため、最小1時間に設定
    hours = max(1, hours)
    
    try:
        rain_fall_sum = get_rain_fall_sum(config, hours)
    except Exception as e:
        logging.warning("Failed to get rain fall data, assuming no rain: %s", e)
        rain_fall_sum = 0.0

    logging.info("Rain fall sum since last watering: %.1f (%d hours)", rain_fall_sum, hours)

    rainfall_judge = rain_fall_sum > config["weather"]["rain_fall"]["sensor"]["threshold"]["sum"]
    logging.info("Rain fall sensor judge: %s", rainfall_judge)

    return (rainfall_judge, rain_fall_sum)


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.webapp.config

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    hours = int(args["-p"])
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)

    my_lib.webapp.config.init(config)
    rasp_water.control.scheduler.init()

    logging.info("Sum of rainfall is %.1f (%d hours)", get_rain_fall_sum(config, hours), hours)

    logging.info("Finish.")
