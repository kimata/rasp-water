"""
水やりメトリクス収集モジュール

このモジュールは以下のメトリクスを収集し、SQLiteデータベースに保存します：
- 水やりをした回数
- 1回あたりの水やりをした時間
- 1回あたりの水やりをした量
- 手動で水やりをしたのか、自動で水やりをしたのか
- エラー発生回数

1日に複数回水やりをした場合、それぞれの水やり毎にデータを記録します。
"""

from __future__ import annotations

import datetime
import logging
import sqlite3
import threading
from pathlib import Path


class MetricsCollector:
    """水やりメトリクス収集クラス"""

    def __init__(self, db_path: Path):
        """コンストラクタ

        Args:
        ----
            db_path: SQLiteデータベースファイルパス

        """
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """データベース初期化"""
        with sqlite3.connect(self.db_path) as conn:
            # 水やり操作のメトリクステーブル
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watering_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    date TEXT NOT NULL,
                    operation_type TEXT NOT NULL CHECK (operation_type IN ('manual', 'auto')),
                    duration_seconds INTEGER NOT NULL,
                    volume_liters REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # エラー発生のメトリクステーブル
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # インデックスの作成
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_watering_metrics_date
                ON watering_metrics(date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_watering_metrics_type
                ON watering_metrics(operation_type)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_metrics_date
                ON error_metrics(date)
            """)

    def _get_today_date(self) -> str:
        """今日の日付を文字列で取得"""
        return datetime.date.today().isoformat()

    def record_watering(
        self,
        operation_type: str,
        duration_seconds: int,
        volume_liters: float | None = None,
        timestamp: datetime.datetime | None = None,
    ):
        """
        水やり操作を記録

        Args:
        ----
            operation_type: "manual" または "auto"
            duration_seconds: 水やりの時間（秒）
            volume_liters: 水やりの量（リットル）、Noneの場合は記録しない
            timestamp: 操作時刻（指定しない場合は現在時刻）

        """
        if timestamp is None:
            timestamp = datetime.datetime.now()

        date = timestamp.date().isoformat()

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO watering_metrics
                    (timestamp, date, operation_type, duration_seconds, volume_liters)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (timestamp, date, operation_type, duration_seconds, volume_liters),
                )

        logging.info(
            "Recorded watering metrics: type=%s, duration=%ds, volume=%s",
            operation_type,
            duration_seconds,
            f"{volume_liters:.2f}L" if volume_liters else "N/A",
        )

    def record_error(
        self,
        error_type: str,
        error_message: str | None = None,
        timestamp: datetime.datetime | None = None,
    ):
        """
        エラー発生を記録

        Args:
        ----
            error_type: エラーの種類（例: "valve_control", "schedule", "sensor"）
            error_message: エラーメッセージ
            timestamp: エラー発生時刻（指定しない場合は現在時刻）

        """
        if timestamp is None:
            timestamp = datetime.datetime.now()

        date = timestamp.date().isoformat()

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO error_metrics (date, error_type, error_message, timestamp)
                    VALUES (?, ?, ?, ?)
                """,
                    (date, error_type, error_message, timestamp),
                )

        logging.info("Recorded error metrics: type=%s, message=%s", error_type, error_message)

    def get_watering_metrics(self, start_date: str, end_date: str) -> list:
        """
        指定期間の水やりメトリクスを取得

        Args:
        ----
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）

        Returns:
        -------
            水やりメトリクスデータのリスト

        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM watering_metrics
                WHERE date BETWEEN ? AND ?
                ORDER BY timestamp
            """,
                (start_date, end_date),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_error_metrics(self, start_date: str, end_date: str) -> list:
        """
        指定期間のエラーメトリクスを取得

        Args:
        ----
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）

        Returns:
        -------
            エラーメトリクスデータのリスト

        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM error_metrics
                WHERE date BETWEEN ? AND ?
                ORDER BY timestamp
            """,
                (start_date, end_date),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_daily_summary(self, date: str) -> dict:
        """
        指定日の統計サマリーを取得

        Args:
        ----
            date: 日付（YYYY-MM-DD形式）

        Returns:
        -------
            統計サマリー（水やり回数、総時間、総量など）

        """
        with sqlite3.connect(self.db_path) as conn:
            # 水やり統計
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_count,
                    SUM(CASE WHEN operation_type = 'manual' THEN 1 ELSE 0 END) as manual_count,
                    SUM(CASE WHEN operation_type = 'auto' THEN 1 ELSE 0 END) as auto_count,
                    SUM(duration_seconds) as total_duration_seconds,
                    SUM(volume_liters) as total_volume_liters,
                    AVG(duration_seconds) as avg_duration_seconds,
                    AVG(volume_liters) as avg_volume_liters
                FROM watering_metrics
                WHERE date = ?
            """,
                (date,),
            )
            watering_stats = dict(cursor.fetchone())

            # エラー統計
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as error_count,
                    COUNT(DISTINCT error_type) as error_type_count
                FROM error_metrics
                WHERE date = ?
            """,
                (date,),
            )
            error_stats = dict(cursor.fetchone())

            return {
                "date": date,
                "watering": watering_stats,
                "errors": error_stats,
            }

    def get_recent_watering_metrics(self, days: int = 30) -> list:
        """
        最近N日間の水やりメトリクスを取得

        Args:
        ----
            days: 取得する日数

        Returns:
        -------
            水やりメトリクスデータのリスト

        """
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)

        return self.get_watering_metrics(start_date.isoformat(), end_date.isoformat())

    def get_recent_error_metrics(self, days: int = 30) -> list:
        """
        最近N日間のエラーメトリクスを取得

        Args:
        ----
            days: 取得する日数

        Returns:
        -------
            エラーメトリクスデータのリスト

        """
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)

        return self.get_error_metrics(start_date.isoformat(), end_date.isoformat())


# グローバルインスタンス
_collector_instance: MetricsCollector | None = None


def get_collector(metrics_data_path) -> MetricsCollector:
    """メトリクス収集インスタンスを取得"""
    global _collector_instance

    if _collector_instance is None:
        db_path = Path(metrics_data_path)
        _collector_instance = MetricsCollector(db_path)
        logging.info("Metrics collector initialized: %s", db_path)

    return _collector_instance


def record_watering(
    operation_type: str,
    duration_seconds: int,
    metrics_data_path,
    volume_liters: float | None = None,
    timestamp: datetime.datetime | None = None,
):
    """水やり操作を記録（便利関数）"""
    get_collector(metrics_data_path).record_watering(
        operation_type, duration_seconds, volume_liters, timestamp
    )


def record_error(
    error_type: str,
    metrics_data_path,
    error_message: str | None = None,
    timestamp: datetime.datetime | None = None,
):
    """エラー発生を記録（便利関数）"""
    get_collector(metrics_data_path).record_error(error_type, error_message, timestamp)