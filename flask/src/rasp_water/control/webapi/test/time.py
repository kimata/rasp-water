#!/usr/bin/env python3

import datetime
import logging
import os

import my_lib.time
import my_lib.webapp.config
import time_machine

import flask

blueprint = flask.Blueprint("rasp-water-test-time", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)


# テスト用の時刻モック状態を保持
_traveler = None


@blueprint.route("/api/test/time/set/<timestamp>", methods=["POST"])
def set_mock_time(timestamp):
    """
    テスト用時刻を設定するAPI

    Args:
        timestamp: Unix timestamp (秒) またはISO形式の日時文字列

    Returns:
        JSON: 設定された時刻情報

    """
    global _traveler  # noqa: PLW0603

    # DUMMY_MODE でない場合は拒否
    if os.environ.get("DUMMY_MODE", "false") != "true":
        return {"error": "Test API is only available in DUMMY_MODE"}, 403

    try:
        # タイムスタンプの解析
        if timestamp.isdigit():
            mock_datetime = datetime.datetime.fromtimestamp(int(timestamp), tz=my_lib.time.get_zoneinfo())
        else:
            # ISO形式の解析
            mock_datetime = datetime.datetime.fromisoformat(timestamp)
            if mock_datetime.tzinfo is None:
                mock_datetime = mock_datetime.replace(tzinfo=my_lib.time.get_zoneinfo())

        # 既存のtravelerを停止
        if _traveler:
            _traveler.stop()

        # time_machineを使用して時刻を設定
        _traveler = time_machine.travel(mock_datetime)
        _traveler.start()

        logging.info("Mock time set to: %s", mock_datetime)

        return {
            "success": True,
            "mock_time": mock_datetime.isoformat(),
            "unix_timestamp": int(mock_datetime.timestamp()),
        }

    except (ValueError, TypeError) as e:
        return {"error": f"Invalid timestamp format: {e}"}, 400


@blueprint.route("/api/test/time/advance/<int:seconds>", methods=["POST"])
def advance_mock_time(seconds):
    """
    モック時刻を指定秒数進める

    Args:
        seconds: 進める秒数

    Returns:
        JSON: 更新された時刻情報

    """
    global _traveler  # noqa: PLW0603

    # DUMMY_MODE でない場合は拒否
    if os.environ.get("DUMMY_MODE", "false") != "true":
        return {"error": "Test API is only available in DUMMY_MODE"}, 403

    if _traveler is None:
        return {"error": "Mock time not set. Use /api/test/time/set first"}, 400

    # 現在の時刻を取得して、新しい時刻を計算
    current_mock_time = my_lib.time.now()
    new_mock_time = current_mock_time + datetime.timedelta(seconds=seconds)

    # 既存のtravelerを停止
    _traveler.stop()

    # 新しい時刻でtravelerを再作成
    _traveler = time_machine.travel(new_mock_time)
    _traveler.start()

    # スケジューラーに現在のスケジュールを再読み込みさせる
    try:
        import rasp_water.control.scheduler
        from rasp_water.control.webapi.schedule import schedule_queue

        current_schedule = rasp_water.control.scheduler.schedule_load()
        schedule_queue.put(current_schedule)
        logging.info("Forced scheduler reload with current schedule")
        
        # スケジューラーの内部時刻同期のため複数回リロード
        for i in range(3):
            schedule_queue.put(current_schedule)
            
    except Exception as e:
        logging.warning("Failed to force scheduler reload: %s", e)

    current_time = my_lib.time.now()
    logging.info("Mock time advanced to: %s", current_time)

    return {
        "success": True,
        "mock_time": current_time.isoformat(),
        "unix_timestamp": int(current_time.timestamp()),
        "advanced_seconds": seconds,
    }


@blueprint.route("/api/test/time/reset", methods=["POST"])
def reset_mock_time():
    """
    モック時刻をリセットして実際の時刻に戻す

    Returns:
        JSON: リセット結果

    """
    global _traveler  # noqa: PLW0603

    # DUMMY_MODE でない場合は拒否
    if os.environ.get("DUMMY_MODE", "false") != "true":
        return {"error": "Test API is only available in DUMMY_MODE"}, 403

    if _traveler:
        _traveler.stop()
        _traveler = None

    logging.info("Mock time reset to real time")

    return {"success": True, "real_time": my_lib.time.now().isoformat()}


@blueprint.route("/api/test/time/current", methods=["GET"])
def get_current_time():
    """
    現在の時刻（モック時刻または実時刻）を取得

    Returns:
        JSON: 現在時刻情報

    """
    # DUMMY_MODE でない場合は拒否
    if os.environ.get("DUMMY_MODE", "false") != "true":
        return {"error": "Test API is only available in DUMMY_MODE"}, 403

    current_time = my_lib.time.now()

    return {
        "current_time": current_time.isoformat(),
        "unix_timestamp": int(current_time.timestamp()),
        "is_mocked": _traveler is not None,
        "mock_time": current_time.isoformat() if _traveler else None,
    }
