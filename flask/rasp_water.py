#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, current_app, Response, send_from_directory,
    Blueprint
)

from functools import wraps
import numpy as np
import re
import sqlite3
import subprocess
import threading
import time
import logging
import json
from crontab import CronTab
import os
import pprint

CTRL_GPIO = 18
FLOW_PATH = '/sys/class/hwmon/hwmon0/device/in4_input'

APP_PATH = '/rasp-water'
ANGULAR_DIST_PATH = '../dist/rasp-water'

EVENT_TYPE_LOG = 'log'
EVENT_TYPE_SCHEDULE = 'schedule'

event_count = {
    EVENT_TYPE_LOG: 0,
    EVENT_TYPE_SCHEDULE: 0,
}

SCHEDULE_MARKER = 'WATER SCHEDULE'
WATER_CTRL_CMD = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'script', 'water_ctrl.py'))

rasp_water = Blueprint('rasp-water', __name__, url_prefix=APP_PATH)

sqlite = sqlite3.connect(':memory:', check_same_thread=False)
sqlite.execute('CREATE TABLE log(date INT, message TEXT)')
sqlite.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

event_lock = threading.Lock()
schedule_lock = threading.Lock()

def parse_cron_line(line):
    match = re.compile(
        '^(#?)\s*(\d{{1,2}})\s+(\d{{1,2}})\s+.+{}\s+(\d+)'.format(re.escape(WATER_CTRL_CMD))
    ).search(str(line))
    
    if match:
        mg = match.groups()
        return {
            'is_active': mg[0] == '',
            'time': ':'.join([mg[2], mg[1]]),
            'period': int(mg[3])
        }
    else:
        match = re.compile(
            '^(#?)\s*@daily.+{}\s+(\d+)'.format(WATER_CTRL_CMD)
        ).search(str(line))
        if match:
            mg = match.groups()

            return {
                'is_active': mg[0] == '',
                'time': '00:00',
                'period': int(mg[1])
            }
        
    return None

def cron_read():
    cron  = CronTab(user=True)
    schedule = []
    for i in range(2):
        item = None
        try:
            item = parse_cron_line(next(cron.find_comment('{} {}'.format(SCHEDULE_MARKER, i))))
        except:
            pass
        if (item == None):
            item = {
                'is_active': False,
                'time': '00:00',
                'period': 0,
            }
        schedule.append(item)
                
    return schedule

def cron_write(schedule):
    cron  = CronTab(user=True)
    for i in range(2):
        cron.remove_all(comment='{} {}'.format(SCHEDULE_MARKER, i))
        job  = cron.new(command='{} {}'.format(WATER_CTRL_CMD, schedule[i]['period']))
        time = schedule[i]['time'].split(':')
        time.reverse()
        
        job.setall('{} {} * * *'.format(*time))
        job.set_comment('{} {}'.format(SCHEDULE_MARKER, i))
        job.enable(schedule[i]['is_active'])
    cron.write()

def log_impl(message):
    global event_count
    with event_lock:
        sqlite.execute('INSERT INTO log VALUES (DATETIME("now", "localtime"), ?)', [message])
        sqlite.execute('DELETE FROM log WHERE date <= DATETIME("now", "localtime", "-2 days")')
        event_count[EVENT_TYPE_LOG] += 1

def log(message):
    threading.Thread(target=log_impl, args=(message,)).start()

def support_jsonp(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            content = callback + '(' + f().data.decode() + ')'
            return current_app.response_class(content, mimetype='application/json')
        else:
            return f(*args, **kwargs)
    return decorated_function

def get_valve_state():
    out = ''
    try:
        out = subprocess.Popen(
            ['raspi-gpio' , 'get', str(CTRL_GPIO) ],
            stdout=subprocess.PIPE,
            shell=False).communicate()[0].decode()
    except:
        pass

    m = re.match(r'GPIO \d+:\s+level=(\d)\s', out)
    if m:
        return {
            'state': m.group(1),
            'result': 'success'
        }
    else:
        return {
            'state': 0,
            'result': 'fail'
        }

def set_valve_state(state):
    try:
        subprocess.Popen(
            ['raspi-gpio' , 'set', str(CTRL_GPIO), 'op', ['dl', 'dh'][state] ],
            stdout=subprocess.PIPE,
            shell=False).communicate()[0]
    except:
        pass

    return get_valve_state()

def get_valve_flow():
    try:
        with open(FLOW_PATH, 'r') as f:
            return {
                'flow': int(f.read()),
                'result': 'success'
            }
    except:
        return {
            'flow': 0,
            'result': 'fail'
        }

@rasp_water.route('/api/valve_ctrl', methods=['GET', 'POST'])
@support_jsonp
def api_valve_ctrl():
    state = request.args.get('set', -1, type=int);
    auto = request.args.get('auto', False, type=bool)
    if state != -1:
        log('{auto}で蛇口を{done}ました。'.format(
            auto='自動' if auto else '手動',
            done=['閉じ', '開き'][state % 2])
        );
        return jsonify(dict({'cmd': 'set'}, **set_valve_state(state % 2)))
    else:
        return jsonify(dict({'cmd': 'get'}, **get_valve_state()))

@rasp_water.route('/api/valve_flow', methods=['GET'])
@support_jsonp
def api_valve_flow():
    return jsonify(dict({'cmd': 'get'}, **get_valve_flow()))

@rasp_water.route('/api/schedule_ctrl', methods=['GET', 'POST'])
@support_jsonp
def api_schedule_ctrl():
    state = request.args.get('set', None)
    if (state != None):
        with schedule_lock:
            cron_write(json.loads(state))

    return jsonify(cron_read())

@rasp_water.route('/api/sysinfo', methods=['GET'])
@support_jsonp
def api_sysinfo():
    date = subprocess.Popen(['date'], stdout=subprocess.PIPE).communicate()[0].decode().strip();
    uptime = subprocess.Popen(['uptime', '-s'], stdout=subprocess.PIPE).communicate()[0].decode().strip();
    loadAverage = re.search(r'load average: (.+)', subprocess.Popen(['uptime'], stdout=subprocess.PIPE).communicate()[0].decode()).group(1)

    return jsonify({
        'date': date,
        'uptime': uptime,
        'loadAverage': loadAverage
    })

@rasp_water.route('/api/log', methods=['GET'])
@support_jsonp
def api_log():
    cur = sqlite.cursor()
    cur.execute('SELECT * FROM log')
    return jsonify({
        'data': cur.fetchall()[::-1]
    })

@rasp_water.route('/api/event', methods=['GET'])
def api_event():
    def event_stream():
        last_count = event_count.copy()
        while True:
            time.sleep(1)
            for method in last_count:
                if (last_count[method] != event_count[method]):
                    yield "data: {}\n\n".format(method)
                    last_count[method] = event_count[method]

    res = Response(event_stream(), mimetype='text/event-stream')
    res.headers.add('Access-Control-Allow-Origin', '*')
    res.headers.add('Cache-Control', 'no-cache')
            
    return res

@rasp_water.route('/', defaults={'filename': 'index.html'})
@rasp_water.route('<path:filename>')
def angular(filename):
    return send_from_directory(ANGULAR_DIST_PATH, filename)
