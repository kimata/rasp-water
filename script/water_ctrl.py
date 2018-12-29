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
            API_ENDPOINT, urllib.parse.urlencode({ 'set': state }))
        )
        status = json.loads(urllib.request.urlopen(req).read().decode())
        return status['result'] == 'success'
    except:
        pass
    
    return False

def water_control(state):
    for i in range(RETRY_COUNT):
        if (water_control_impl(state)): return;

period = int(sys.argv[1])

print('{}    {} 分間水やりをします。'.format(datetime.now(), period))

print('{}    開始。'.format(datetime.now()))
water_control(1)

print('{}    {} 分間待ちます。'.format(datetime.now(), period))
time.sleep(period * 60)

print('{}    終了。'.format(datetime.now()))
water_control(0)



