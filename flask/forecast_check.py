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

YAHOO_API_ENDPOINT='https://map.yahooapis.jp/weather/V1/place'
OPENWEATHERMAP_API_ENDPOINT='http://api.openweathermap.org/data/2.5/forecast'

def get_weather_info_yahoo():
    params = {
        'appid': YAHOO_APP_ID,
        'coordinates': ','.join(map(str,[POINT_LON, POINT_LAT])),
        'output': 'json',
        'past': 2,
    }
    url = '{}?{}'.format(YAHOO_API_ENDPOINT, urllib.parse.urlencode(params))

    return json.loads(urllib.request.urlopen(url).read().decode('utf-8'))

def check_rain_fall_yahoo():
    json = get_weather_info_yahoo()
    weather_info = json['Feature'][0]['Property']['WeatherList']['Weather']
    # NOTE: YAhoo の場合，1 時間後までしか情報がとれないので，4 時間前以降を参考にする
    rainfall_list = map(lambda x: x['Rainfall'],
                        filter(lambda x:
                               (datetime.now() -
                                datetime.strptime(x['Date'], '%Y%m%d%H%M')).total_seconds() / (60*60) < 4,
                               weather_info))
    return functools.reduce(lambda x, y: x + y, rainfall_list)

def get_weather_info_openweathermap():
    params = {
        'APPID': OPENWEATHERMAP_APP_ID,
        'id': OPENWEATHERMAP_CITY_ID,
    }
    url = '{}?{}'.format(OPENWEATHERMAP_API_ENDPOINT, urllib.parse.urlencode(params))

    return json.loads(urllib.request.urlopen(url).read().decode('utf-8'))

def check_rain_fall_openweathermap():
    json = get_weather_info_openweathermap()
    # OpenWeatherMap の場合，かなり先まで取得できるので，8 時間後までを参考にする
    rainfall_list = \
        list(map(lambda x: [ timezone('Asia/Tokyo').localize(datetime.fromtimestamp(x['dt'])).strftime('%c %z'),
                             x['rain']['3h'] ],
                 filter(lambda x: ((datetime.fromtimestamp(x['dt']) -
                                    datetime.now()).total_seconds() / (60*60)) < 8,
                        filter(lambda x: 'rain' in x, json['list']))))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'forecast.log'), mode='a') as f:
        print('{} {} => {}'.format(
            datetime.now(), list(rainfall_list),
            functools.reduce(lambda x, y: x + y[1], rainfall_list, 0.0)
        ), file=f)

    return functools.reduce(lambda x, y: x + y[1], rainfall_list, 0.0)

def is_rain_forecast():
    try:
        # OpenWeatherMap は値がおかしいことが度々あったので，Yahoo を採用する
        return check_rain_fall_yahoo() > 2
    except:
        pass

    return False

if __name__ == '__main__':
    print(is_rain_forecast())

