#!/usr/bin/env python3

import datetime
import logging
import os
from unittest.mock import patch

import flask
import my_lib.time
import rasp_water.scheduler


blueprint = flask.Blueprint("rasp-water-test-time", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)

# テスト用の時刻モック状態を保持
_mock_time = None
_time_patcher = None
_schedule_patcher = None
_datetime_patcher = None


def is_dummy_mode():
    """DUMMY_MODEかどうかを判定"""
    return os.environ.get("DUMMY_MODE", "false").lower() == "true"


def get_mock_time():
    """モック時刻を取得（DUMMY_MODEでない場合は実際の時刻）"""
    if is_dummy_mode() and _mock_time is not None:
        return _mock_time
    return my_lib.time.now()


@blueprint.route("/api/test/time/set/<iso_time>", methods=["POST"])
def set_time(iso_time):
    """テスト用: モック時刻を設定（DUMMY_MODEでのみ動作）"""
    global _mock_time, _time_patcher, _schedule_patcher, _datetime_patcher
    
    if not is_dummy_mode():
        return flask.jsonify({"error": "Only available in DUMMY_MODE"}), 400
    
    try:
        # ISO形式の時刻文字列をパース
        _mock_time = datetime.datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        # タイムゾーンを現在のタイムゾーンに変換
        if _mock_time.tzinfo is not None:
            _mock_time = _mock_time.astimezone(my_lib.time.get_zoneinfo())
        else:
            _mock_time = _mock_time.replace(tzinfo=my_lib.time.get_zoneinfo())
        
        # 既存のパッチャーがあれば停止
        if _time_patcher:
            _time_patcher.stop()
        if _schedule_patcher:
            _schedule_patcher.stop()
        if _datetime_patcher:
            _datetime_patcher.stop()

        # my_lib.time.now() を全体的にモック
        _time_patcher = patch("my_lib.time.now", return_value=_mock_time)
        _time_patcher.start()

        # スケジューラーモジュールでもパッチ
        _schedule_patcher = patch("rasp_water.scheduler.my_lib.time.now", return_value=_mock_time)
        _schedule_patcher.start()

        # scheduleライブラリのdatetime.datetime.nowもパッチ（タイムゾーン対応）
        def mock_datetime_now(tz=None):
            if tz is None:
                return _mock_time.replace(tzinfo=None)
            else:
                return _mock_time.astimezone(tz)

        _datetime_patcher = patch("datetime.datetime.now", side_effect=mock_datetime_now)
        _datetime_patcher.start()

        logging.info("Mock time set to: %s", _mock_time)
        
        return flask.jsonify({"status": "success", "mock_time": _mock_time.isoformat()}), 200
    except ValueError as e:
        return flask.jsonify({"error": f"Invalid time format: {e}"}), 400


@blueprint.route("/api/test/time/advance/<int:seconds>", methods=["POST"])
def advance_time(seconds):
    """テスト用: モック時刻を指定秒数進める（DUMMY_MODEでのみ動作）"""
    global _mock_time, _time_patcher, _schedule_patcher, _datetime_patcher
    
    if not is_dummy_mode():
        return flask.jsonify({"error": "Only available in DUMMY_MODE"}), 400
    
    if _mock_time is None:
        _mock_time = my_lib.time.now()
    
    _mock_time += datetime.timedelta(seconds=seconds)
    
    # パッチャーを更新
    if _time_patcher:
        _time_patcher.stop()
    if _schedule_patcher:
        _schedule_patcher.stop()
    if _datetime_patcher:
        _datetime_patcher.stop()

    _time_patcher = patch("my_lib.time.now", return_value=_mock_time)
    _time_patcher.start()

    _schedule_patcher = patch("rasp_water.scheduler.my_lib.time.now", return_value=_mock_time)
    _schedule_patcher.start()

    def mock_datetime_now(tz=None):
        if tz is None:
            return _mock_time.replace(tzinfo=None)
        else:
            return _mock_time.astimezone(tz)

    _datetime_patcher = patch("datetime.datetime.now", side_effect=mock_datetime_now)
    _datetime_patcher.start()

    logging.info("Mock time advanced to: %s", _mock_time)
    
    return flask.jsonify({"status": "success", "mock_time": _mock_time.isoformat()}), 200


@blueprint.route("/api/test/time/reset", methods=["POST"])
def reset_time():
    """テスト用: モック時刻をリセット（DUMMY_MODEでのみ動作）"""
    global _mock_time, _time_patcher, _schedule_patcher, _datetime_patcher
    
    if not is_dummy_mode():
        return flask.jsonify({"error": "Only available in DUMMY_MODE"}), 400
    
    if _time_patcher:
        _time_patcher.stop()
        _time_patcher = None

    if _schedule_patcher:
        _schedule_patcher.stop()
        _schedule_patcher = None

    if _datetime_patcher:
        _datetime_patcher.stop()
        _datetime_patcher = None

    _mock_time = None

    logging.info("Mock time reset to real time")
    
    return flask.jsonify({"status": "success"}), 200


@blueprint.route("/api/test/time/current", methods=["GET"])
def get_current_time():
    """テスト用: 現在のモック時刻を取得"""
    if not is_dummy_mode():
        return flask.jsonify({"error": "Only available in DUMMY_MODE"}), 400
    
    current_time = get_mock_time()
    return flask.jsonify({"current_time": current_time.isoformat(), "is_mock": _mock_time is not None}), 200
