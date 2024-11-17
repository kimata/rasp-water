#!/usr/bin/env python3
import datetime
import functools
import json
import logging

import my_lib.webapp.config
import requests

YAHOO_API_ENDPOINT = "https://map.yahooapis.jp/weather/V1/place"


def get_weather_info_yahoo(config):
    try:
        params = {
            "appid": config["weather"]["rain_fall"]["forecast"]["yahoo"]["id"],
            "coordinates": ",".join(
                map(
                    str,
                    [
                        config["weather"]["rain_fall"]["forecast"]["point"]["lon"],
                        config["weather"]["rain_fall"]["forecast"]["point"]["lat"],
                    ],
                )
            ),
            "output": "json",
            "past": 2,
        }

        res = requests.get(YAHOO_API_ENDPOINT, params=params, timeout=5)

        if res.status_code != 200:
            logging.warning("Failed to fetch weather info from Yahoo")
            return None

        return json.loads(res.content)["Feature"][0]["Property"]["WeatherList"]["Weather"]
    except Exception:
        logging.warning("Failed to fetch weather info from Yahoo")
        return None


def get_rain_fall(config):
    weather_info = get_weather_info_yahoo(config)

    if weather_info is None:
        return (False, 0)

    # NOTE: YAhoo の場合，1 時間後までしか情報がとれないことに注意
    rainfall_list = [
        x["Rainfall"]
        for x in filter(
            lambda x: (
                datetime.datetime.now(my_lib.webapp.config.TIMEZONE)
                - datetime.datetime.strptime(x["Date"], "%Y%m%d%H%M").astimezone(
                    my_lib.webapp.config.TIMEZONE_PYTZ
                )
            ).total_seconds()
            / (60 * 60)
            < config["weather"]["rain_fall"]["forecast"]["threshold"]["before_hour"],
            weather_info,
        )
    ]

    rainfall_sum = functools.reduce(lambda x, y: x + y, rainfall_list)

    logging.info(
        "Rain fall forecast sum: %d (%s)", rainfall_sum, ", ".join(f"{num:.1f}" for num in rainfall_list)
    )

    rainfall_judge = rainfall_sum > config["weather"]["rain_fall"]["forecast"]["threshold"]["sum"]
    logging.info("Rain fall forecast judge: %s", rainfall_judge)

    return (rainfall_judge, rainfall_sum)


if __name__ == "__main__":
    import my_lib.config
    import my_lib.logger

    my_lib.logger.init("test", level=logging.INFO)

    config = my_lib.load()

    print(get_rain_fall(config))  # noqa: T201
