#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import urllib.request
import functools
import json
from pytz import timezone
from dateutil import parser
import pprint

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
    rainfall_list = map(lambda x: x['Rainfall'], weather_info)

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
    rainfall_list = map(lambda x: x['rain']['3h'],
                        filter(lambda x: '3h' in x['rain'], json['list']))

    return functools.reduce(lambda x, y: x + y, rainfall_list)

def is_rain_forecast():
    return check_rain_fall_openweathermap() > 5

if __name__ == '__main__':
    print(is_rain_forecast())

