#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import urllib.request
import functools
import os
import json
from pytz import timezone
from datetime import datetime
from dateutil import parser

from config import *

YAHOO_API_ENDPOINT = "https://map.yahooapis.jp/weather/V1/place"


def get_weather_info_yahoo():
    params = {
        "appid": YAHOO_APP_ID,
        "coordinates": ",".join(map(str, [POINT_LON, POINT_LAT])),
        "output": "json",
        "past": 2,
    }
    url = "{}?{}".format(YAHOO_API_ENDPOINT, urllib.parse.urlencode(params))

    return json.loads(urllib.request.urlopen(url).read().decode("utf-8"))


def check_rain_fall_yahoo():
    json = get_weather_info_yahoo()
    weather_info = json["Feature"][0]["Property"]["WeatherList"]["Weather"]
    # NOTE: YAhoo の場合，1 時間後までしか情報がとれないので，4 時間前以降を参考にする
    rainfall_list = map(
        lambda x: x["Rainfall"],
        filter(
            lambda x: (
                datetime.now() - datetime.strptime(x["Date"], "%Y%m%d%H%M")
            ).total_seconds()
            / (60 * 60)
            < 4,
            weather_info,
        ),
    )
    return functools.reduce(lambda x, y: x + y, rainfall_list)


def is_rain_forecast():
    try:
        # OpenWeatherMap は値がおかしいことが度々あったので，Yahoo を採用する
        return check_rain_fall_yahoo() > 2
    except:
        pass

    return False


if __name__ == "__main__":
    print(is_rain_forecast())
