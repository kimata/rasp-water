#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import functools
import json
import logging

import requests

YAHOO_API_ENDPOINT = "https://map.yahooapis.jp/weather/V1/place"


def get_weather_info_yahoo(config):
    try:
        params = {
            "appid": config["weather"]["yahoo"]["id"],
            "coordinates": ",".join(
                map(
                    str,
                    [
                        config["weather"]["point"]["lon"],
                        config["weather"]["point"]["lat"],
                    ],
                )
            ),
            "output": "json",
            "past": 2,
        }

        res = requests.get(YAHOO_API_ENDPOINT, params=params)

        if res.status_code != 200:
            logging.warning("Failed to fetch weather info from Yahoo")
            return None

        return json.loads(res.content)["Feature"][0]["Property"]["WeatherList"]["Weather"]
    except:
        logging.warning("Failed to fetch weather info from Yahoo")
        return None


def get_rain_fall(config):
    weather_info = get_weather_info_yahoo(config)

    if weather_info is None:
        return False

    # NOTE: YAhoo の場合，1 時間後までしか情報がとれないので，4 時間前以降を参考にする
    rainfall_list = list(
        map(
            lambda x: x["Rainfall"],
            filter(
                lambda x: (
                    datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=+9), "JST"))
                    - datetime.datetime.strptime(x["Date"], "%Y%m%d%H%M").replace(
                        tzinfo=datetime.timezone(datetime.timedelta(hours=+9), "JST")
                    )
                ).total_seconds()
                / (60 * 60)
                < config["weather"]["rain_fall"]["before_hour"],
                weather_info,
            ),
        )
    )

    rainfall_total = functools.reduce(lambda x, y: x + y, rainfall_list)

    logging.info(
        "Rain fall total: {rainfall_total} ({rainfall_list})".format(
            rainfall_total=rainfall_total, rainfall_list=rainfall_list
        )
    )

    rainfall_judge = rainfall_total > config["weather"]["rain_fall"]["threshold"]
    logging.info("Rain fall judge: {rainfall_judge}".format(rainfall_judge=rainfall_judge))

    return rainfall_judge


if __name__ == "__main__":
    import logger
    from config import load_config

    logger.init("test", level=logging.INFO)

    config = load_config()
    print(get_rain_fall(config))
