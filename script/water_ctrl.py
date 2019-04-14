#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import urllib.request
import time
import sys
import json
from datetime import datetime

API_ENDPOINT = 'http://127.0.0.1:5000/rasp-water/api/valve_ctrl'
RETRY_COUNT = 5

def water_control_impl(state):
    try:
        req = urllib.request.Request('{}?{}'.format(
            API_ENDPOINT, urllib.parse.urlencode({
                'set': state,
                'auto': True,
            }))
        )
        status = json.loads(urllib.request.urlopen(req).read().decode())
        return (status['result'] == 'success', status['pending'])
    except:
        pass

    return False

def water_control(state):
    for i in range(RETRY_COUNT):
        result = water_control_impl(state)
        if (result != False): return result
    return False

period = int(sys.argv[1])

print('{}    {} 分間水やりをします。'.format(datetime.now(), period))

print('{}    開始。'.format(datetime.now()))
result = water_control(1)

if result == False:
    print('{}    制御に失敗しました。'.format(datetime.now()))
    sys.exit(-1)
if result[1]:
    print('{}    雨により、自動での水やりを見合わせました。'.format(datetime.now()))
    sys.exit(0)

print('{}    {} 分間待ちます。'.format(datetime.now(), period))
time.sleep(period * 60)

print('{}    終了。'.format(datetime.now()))
water_control(0)



