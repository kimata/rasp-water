#!/usr/bin/env python3
"""
水やりメトリクス表示ページ

水やり操作の統計情報とグラフを表示するWebページを提供します。
"""

from __future__ import annotations

import datetime
import io
import json
import logging
from collections import defaultdict

import my_lib.webapp.config
import rasp_water.metrics.collector
from PIL import Image, ImageDraw

import flask

blueprint = flask.Blueprint("metrics", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)


@blueprint.route("/api/metrics", methods=["GET"])
def metrics_view():
    """メトリクスダッシュボードページを表示"""
    try:
        # 設定からメトリクスデータパスを取得
        config = flask.current_app.config["CONFIG"]
        metrics_data_path = config.get("metrics", {}).get("data")

        # データベースファイルの存在確認
        if not metrics_data_path:
            return flask.Response(
                "<html><body><h1>メトリクス設定が見つかりません</h1>"
                "<p>config.yamlでmetricsセクションが設定されていません。</p></body></html>",
                mimetype="text/html",
                status=503,
            )

        from pathlib import Path

        db_path = Path(metrics_data_path)
        if not db_path.exists():
            return flask.Response(
                f"<html><body><h1>メトリクスデータベースが見つかりません</h1>"
                f"<p>データベースファイル: {db_path}</p>"
                f"<p>システムが十分に動作してからメトリクスが生成されます。</p></body></html>",
                mimetype="text/html",
                status=503,
            )

        # メトリクス収集器を取得
        collector = rasp_water.metrics.collector.get_collector(metrics_data_path)

        # 最近30日間のデータを取得
        watering_metrics = collector.get_recent_watering_metrics(days=30)
        error_metrics = collector.get_recent_error_metrics(days=30)

        # 統計データを生成
        stats = generate_statistics(watering_metrics, error_metrics)

        # 時系列データを準備
        time_series_data = prepare_time_series_data(watering_metrics)

        # HTMLを生成
        html_content = generate_metrics_html(stats, time_series_data)

        return flask.Response(html_content, mimetype="text/html")

    except Exception as e:
        logging.exception("メトリクス表示の生成エラー")
        return flask.Response(f"エラー: {e!s}", mimetype="text/plain", status=500)


@blueprint.route("/favicon.ico", methods=["GET"])
def favicon():
    """動的生成された水やりメトリクス用favicon.icoを返す"""
    try:
        # 水やりメトリクスアイコンを生成
        img = generate_watering_metrics_icon()

        # ICO形式で出力
        output = io.BytesIO()
        img.save(output, format="ICO", sizes=[(32, 32)])
        output.seek(0)

        return flask.Response(
            output.getvalue(),
            mimetype="image/x-icon",
            headers={
                "Cache-Control": "public, max-age=3600",  # 1時間キャッシュ
                "Content-Type": "image/x-icon",
            },
        )
    except Exception:
        logging.exception("favicon生成エラー")
        return flask.Response("", status=500)


def generate_watering_metrics_icon():
    """水やりメトリクス用のアイコンを動的生成（アンチエイリアス対応）"""
    # アンチエイリアスのため4倍サイズで描画してから縮小
    scale = 4
    size = 32
    large_size = size * scale

    # 大きなサイズで描画
    img = Image.new("RGBA", (large_size, large_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景円（水を表す青色）
    margin = 2 * scale
    draw.ellipse(
        [margin, margin, large_size - margin, large_size - margin],
        fill=(52, 152, 219, 255),  # 水色
        outline=(41, 128, 185, 255),
        width=2 * scale,
    )

    # 水滴を描画
    drop_center_x = large_size // 2
    drop_center_y = large_size // 2 - 4 * scale
    drop_width = 8 * scale
    drop_height = 10 * scale

    # 水滴の形状（上部は円、下部は三角形）
    # 上部の円
    draw.ellipse(
        [
            drop_center_x - drop_width // 2,
            drop_center_y,
            drop_center_x + drop_width // 2,
            drop_center_y + drop_width,
        ],
        fill=(255, 255, 255, 255),
    )

    # 下部の三角形
    triangle_points = [
        (drop_center_x - drop_width // 2, drop_center_y + drop_width // 2),
        (drop_center_x + drop_width // 2, drop_center_y + drop_width // 2),
        (drop_center_x, drop_center_y + drop_height),
    ]
    draw.polygon(triangle_points, fill=(255, 255, 255, 255))

    # グラフの線を描画（座標を4倍に拡大）
    points = [
        (8 * scale, 22 * scale),
        (12 * scale, 18 * scale),
        (16 * scale, 20 * scale),
        (20 * scale, 16 * scale),
        (24 * scale, 14 * scale),
    ]

    # 折れ線グラフ
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=(255, 255, 255, 200), width=1 * scale)

    # 32x32に縮小してアンチエイリアス効果を得る
    return img.resize((size, size), Image.LANCZOS)


def generate_statistics(watering_metrics: list[dict], error_metrics: list[dict]) -> dict:
    """メトリクスデータから統計情報を生成"""
    if not watering_metrics:
        return {
            "total_days": 0,
            "total_watering_count": 0,
            "manual_watering_count": 0,
            "auto_watering_count": 0,
            "total_duration_minutes": 0,
            "total_volume_liters": 0,
            "avg_duration_minutes": 0,
            "avg_volume_liters": 0,
            "avg_flow_rate": 0,
            "error_count": len(error_metrics),
        }

    # 日付ごとのデータを集計
    unique_dates = {op.get("date") for op in watering_metrics if op.get("date")}

    # 各種カウントと合計値を計算
    total_watering_count = len(watering_metrics)
    manual_watering_count = sum(
        1 for op in watering_metrics if op.get("operation_type") == "manual"
    )
    auto_watering_count = sum(
        1 for op in watering_metrics if op.get("operation_type") == "auto"
    )

    total_duration_seconds = sum(
        op.get("duration_seconds", 0) for op in watering_metrics
    )
    total_volume_liters = sum(
        op.get("volume_liters", 0) for op in watering_metrics if op.get("volume_liters") is not None
    )

    # 平均値を計算
    avg_duration_seconds = total_duration_seconds / total_watering_count if total_watering_count > 0 else 0
    avg_volume_liters = total_volume_liters / total_watering_count if total_watering_count > 0 else 0

    # 流量（リットル/秒）を計算
    avg_flow_rate = total_volume_liters / total_duration_seconds if total_duration_seconds > 0 else 0

    return {
        "total_days": len(unique_dates),
        "total_watering_count": total_watering_count,
        "manual_watering_count": manual_watering_count,
        "auto_watering_count": auto_watering_count,
        "total_duration_minutes": total_duration_seconds / 60,
        "total_volume_liters": total_volume_liters,
        "avg_duration_minutes": avg_duration_seconds / 60,
        "avg_volume_liters": avg_volume_liters,
        "avg_flow_rate": avg_flow_rate,
        "error_count": len(error_metrics),
    }


def prepare_time_series_data(watering_metrics: list[dict]) -> dict:
    """時系列データを準備"""
    # 日付ごとのデータを集計
    daily_data = defaultdict(lambda: {
        "count": 0,
        "manual_count": 0,
        "auto_count": 0,
        "duration_seconds": 0,
        "volume_liters": 0,
        "watering_list": []
    })

    for op in watering_metrics:
        date = op.get("date")
        if date:
            daily_data[date]["count"] += 1
            daily_data[date]["duration_seconds"] += op.get("duration_seconds", 0)
            
            if op.get("volume_liters") is not None:
                daily_data[date]["volume_liters"] += op.get("volume_liters", 0)
            
            if op.get("operation_type") == "manual":
                daily_data[date]["manual_count"] += 1
            else:
                daily_data[date]["auto_count"] += 1
                
            # 個別の水やりデータを保存（流量計算用）
            daily_data[date]["watering_list"].append({
                "duration_seconds": op.get("duration_seconds", 0),
                "volume_liters": op.get("volume_liters", 0)
            })

    # 週ごとのデータを集計
    weekly_data = defaultdict(lambda: {
        "count": 0,
        "manual_count": 0,
        "auto_count": 0,
        "duration_seconds": 0,
        "volume_liters": 0,
        "watering_list": []
    })

    for date_str, data in daily_data.items():
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        week_start = date_obj - datetime.timedelta(days=date_obj.weekday())
        week_key = week_start.isoformat()
        
        weekly_data[week_key]["count"] += data["count"]
        weekly_data[week_key]["manual_count"] += data["manual_count"]
        weekly_data[week_key]["auto_count"] += data["auto_count"]
        weekly_data[week_key]["duration_seconds"] += data["duration_seconds"]
        weekly_data[week_key]["volume_liters"] += data["volume_liters"]
        weekly_data[week_key]["watering_list"].extend(data["watering_list"])

    # ソートして配列に変換
    sorted_dates = sorted(daily_data.keys())
    sorted_weeks = sorted(weekly_data.keys())

    # 日別データ
    daily_labels = sorted_dates
    daily_volumes = [daily_data[date]["volume_liters"] for date in sorted_dates]
    daily_counts = [daily_data[date]["count"] for date in sorted_dates]
    daily_durations = [daily_data[date]["duration_seconds"] / 60 for date in sorted_dates]  # 分に変換
    daily_manual_counts = [daily_data[date]["manual_count"] for date in sorted_dates]

    # 週別データ
    weekly_labels = [f"{week}週" for week in sorted_weeks]
    weekly_volumes = [weekly_data[week]["volume_liters"] for week in sorted_weeks]
    weekly_counts = [weekly_data[week]["count"] for week in sorted_weeks]
    weekly_durations = [weekly_data[week]["duration_seconds"] / 60 for week in sorted_weeks]  # 分に変換
    weekly_manual_counts = [weekly_data[week]["manual_count"] for week in sorted_weeks]

    # 流量データ（リットル/秒）
    flow_rates = []
    flow_labels = []
    for op in watering_metrics:
        if op.get("duration_seconds", 0) > 0 and op.get("volume_liters") is not None:
            flow_rate = op.get("volume_liters", 0) / op.get("duration_seconds", 0)
            flow_rates.append(flow_rate)
            flow_labels.append(op.get("timestamp", ""))

    return {
        "daily": {
            "labels": daily_labels,
            "volumes": daily_volumes,
            "counts": daily_counts,
            "durations": daily_durations,
            "manual_counts": daily_manual_counts,
        },
        "weekly": {
            "labels": weekly_labels,
            "volumes": weekly_volumes,
            "counts": weekly_counts,
            "durations": weekly_durations,
            "manual_counts": weekly_manual_counts,
        },
        "flow": {
            "labels": flow_labels,
            "rates": flow_rates,
        }
    }


def generate_metrics_html(stats: dict, time_series_data: dict) -> str:
    """Bulma CSSを使用したメトリクスHTMLを生成"""
    chart_data_json = json.dumps(time_series_data)

    # URL_PREFIXを取得してfaviconパスを構築
    favicon_path = f"{my_lib.webapp.config.URL_PREFIX}/favicon.ico"

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>水やり メトリクス ダッシュボード</title>
    <link rel="icon" type="image/x-icon" href="{favicon_path}">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .metrics-card {{ margin-bottom: 1rem; }}
        @media (max-width: 768px) {{
            .metrics-card {{ margin-bottom: 0.75rem; }}
        }}
        .stat-number {{ font-size: 2rem; font-weight: bold; }}
        .chart-container {{ position: relative; height: 350px; margin: 0.5rem 0; }}
        @media (max-width: 768px) {{
            .chart-container {{ height: 300px; margin: 0.25rem 0; }}
            .container.is-fluid {{ padding: 0.25rem !important; }}
            .section {{ padding: 0.5rem 0.25rem !important; }}
            .card {{ margin-bottom: 1rem !important; }}
            .columns {{ margin: 0 !important; }}
            .column {{ padding: 0.25rem !important; }}
        }}
        .japanese-font {{
            font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                         "Noto Sans CJK JP", "Yu Gothic", sans-serif;
        }}
        .permalink-header {{
            position: relative;
            display: inline-block;
        }}
        .permalink-icon {{
            opacity: 0;
            transition: opacity 0.2s ease-in-out;
            cursor: pointer;
            color: #4a90e2;
            margin-left: 0.5rem;
            font-size: 0.8em;
        }}
        .permalink-header:hover .permalink-icon {{
            opacity: 1;
        }}
        .permalink-icon:hover {{
            color: #357abd;
        }}
    </style>
</head>
<body class="japanese-font">
    <div class="container is-fluid" style="padding: 0.5rem;">
        <section class="section" style="padding: 1rem 0.5rem;">
            <div class="container" style="max-width: 100%; padding: 0;">
                <h1 class="title is-2 has-text-centered">
                    <span class="icon is-large"><i class="fas fa-tint"></i></span>
                    水やり メトリクス ダッシュボード
                </h1>
                <p class="subtitle has-text-centered">過去30日間の水やり統計</p>

                <!-- 基本統計 -->
                {generate_basic_stats_section(stats)}

                <!-- 日別時系列分析 -->
                {generate_daily_time_series_section()}

                <!-- 週別時系列分析 -->
                {generate_weekly_time_series_section()}

                <!-- 流量分析 -->
                {generate_flow_analysis_section()}
            </div>
        </section>
    </div>

    <script>
        const chartData = {chart_data_json};

        // チャート生成
        generateDailyCharts();
        generateWeeklyCharts();
        generateFlowChart();

        // パーマリンク機能を初期化
        initializePermalinks();

        {generate_chart_javascript()}
    </script>
</html>
    """


def generate_basic_stats_section(stats: dict) -> str:
    """基本統計セクションのHTML生成"""
    return f"""
    <div class="section">
        <h2 class="title is-4 permalink-header" id="basic-stats">
            <span class="icon"><i class="fas fa-chart-bar"></i></span>
            基本統計（過去30日間）
            <span class="permalink-icon" onclick="copyPermalink('basic-stats')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">水やり実績</p>
                    </div>
                    <div class="card-content">
                        <div class="columns is-multiline">
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">総水やり回数</p>
                                    <p class="stat-number has-text-primary">{stats["total_watering_count"]:,}</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">🔧 手動水やり</p>
                                    <p class="stat-number has-text-info">{stats["manual_watering_count"]:,}</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">🤖 自動水やり</p>
                                    <p class="stat-number has-text-success">{stats["auto_watering_count"]:,}</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">総散水量</p>
                                    <p class="stat-number has-text-link">{stats["total_volume_liters"]:.1f} L</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">総散水時間</p>
                                    <p class="stat-number has-text-warning">{stats["total_duration_minutes"]:.1f} 分</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">エラー回数</p>
                                    <p class="stat-number has-text-danger">{stats["error_count"]:,}</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">平均散水量/回</p>
                                    <p class="stat-number">{stats["avg_volume_liters"]:.2f} L</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">平均散水時間/回</p>
                                    <p class="stat-number">{stats["avg_duration_minutes"]:.1f} 分</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">平均流量</p>
                                    <p class="stat-number">{stats["avg_flow_rate"]:.3f} L/秒</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_daily_time_series_section() -> str:
    """日別時系列分析セクションのHTML生成"""
    return """
    <div class="section">
        <h2 class="title is-4 permalink-header" id="daily-analysis">
            <span class="icon"><i class="fas fa-calendar-day"></i></span> 日別時系列分析
            <span class="permalink-icon" onclick="copyPermalink('daily-analysis')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="daily-volume">
                            💧 1日あたりの散水量
                            <span class="permalink-icon" onclick="copyPermalink('daily-volume')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="dailyVolumeChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="daily-count">
                            📊 1日あたりの散水回数
                            <span class="permalink-icon" onclick="copyPermalink('daily-count')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="dailyCountChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="daily-duration">
                            ⏱️ 1日あたりの散水時間
                            <span class="permalink-icon" onclick="copyPermalink('daily-duration')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="dailyDurationChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_weekly_time_series_section() -> str:
    """週別時系列分析セクションのHTML生成"""
    return """
    <div class="section">
        <h2 class="title is-4 permalink-header" id="weekly-analysis">
            <span class="icon"><i class="fas fa-calendar-week"></i></span> 週別時系列分析
            <span class="permalink-icon" onclick="copyPermalink('weekly-analysis')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="weekly-volume">
                            💧 1週間あたりの散水量
                            <span class="permalink-icon" onclick="copyPermalink('weekly-volume')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="weeklyVolumeChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="weekly-count">
                            📊 1週間あたりの散水回数
                            <span class="permalink-icon" onclick="copyPermalink('weekly-count')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="weeklyCountChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="weekly-duration">
                            ⏱️ 1週間あたりの散水時間
                            <span class="permalink-icon" onclick="copyPermalink('weekly-duration')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="weeklyDurationChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="weekly-manual">
                            🔧 1週間あたりの手動散水回数
                            <span class="permalink-icon" onclick="copyPermalink('weekly-manual')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="weeklyManualChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_flow_analysis_section() -> str:
    """流量分析セクションのHTML生成"""
    return """
    <div class="section">
        <h2 class="title is-4 permalink-header" id="flow-analysis">
            <span class="icon"><i class="fas fa-water"></i></span> 流量分析
            <span class="permalink-icon" onclick="copyPermalink('flow-analysis')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="flow-rate">
                            🚰 1秒あたりの散水量（流量）
                            <span class="permalink-icon" onclick="copyPermalink('flow-rate')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="flowRateChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_chart_javascript() -> str:
    """チャート生成用JavaScriptを生成"""
    return """
        function initializePermalinks() {
            // ページ読み込み時にハッシュがある場合はスクロール
            if (window.location.hash) {
                const element = document.querySelector(window.location.hash);
                if (element) {
                    setTimeout(() => {
                        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }, 500); // チャート描画完了を待つ
                }
            }
        }

        function copyPermalink(sectionId) {
            const url = window.location.origin + window.location.pathname + '#' + sectionId;

            // Clipboard APIを使用してURLをコピー
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(url).then(() => {
                    showCopyNotification();
                }).catch(err => {
                    console.error('Failed to copy: ', err);
                    fallbackCopyToClipboard(url);
                });
            } else {
                // フォールバック
                fallbackCopyToClipboard(url);
            }

            // URLにハッシュを設定（履歴には残さない）
            window.history.replaceState(null, null, '#' + sectionId);
        }

        function fallbackCopyToClipboard(text) {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            try {
                document.execCommand('copy');
                showCopyNotification();
            } catch (err) {
                console.error('Fallback: Failed to copy', err);
                // 最後の手段として、プロンプトでURLを表示
                prompt('URLをコピーしてください:', text);
            }

            document.body.removeChild(textArea);
        }

        function showCopyNotification() {
            // 通知要素を作成
            const notification = document.createElement('div');
            notification.textContent = 'パーマリンクをコピーしました！';
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #23d160;
                color: white;
                padding: 12px 20px;
                border-radius: 4px;
                z-index: 1000;
                font-size: 14px;
                font-weight: 500;
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                transition: opacity 0.3s ease-in-out;
            `;

            document.body.appendChild(notification);

            // 3秒後にフェードアウト
            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => {
                    if (notification.parentNode) {
                        document.body.removeChild(notification);
                    }
                }, 300);
            }, 3000);
        }

        function generateDailyCharts() {
            // 日別散水量チャート
            const dailyVolumeCtx = document.getElementById('dailyVolumeChart');
            if (dailyVolumeCtx && chartData.daily && chartData.daily.labels.length > 0) {
                new Chart(dailyVolumeCtx, {
                    type: 'bar',
                    data: {
                        labels: chartData.daily.labels,
                        datasets: [{
                            label: '散水量 (L)',
                            data: chartData.daily.volumes,
                            backgroundColor: 'rgba(52, 152, 219, 0.7)',
                            borderColor: 'rgba(52, 152, 219, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: '散水量 (リットル)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '日付'
                                }
                            }
                        }
                    }
                });
            }

            // 日別散水回数チャート
            const dailyCountCtx = document.getElementById('dailyCountChart');
            if (dailyCountCtx && chartData.daily && chartData.daily.labels.length > 0) {
                new Chart(dailyCountCtx, {
                    type: 'line',
                    data: {
                        labels: chartData.daily.labels,
                        datasets: [{
                            label: '散水回数',
                            data: chartData.daily.counts,
                            borderColor: 'rgba(46, 204, 113, 1)',
                            backgroundColor: 'rgba(46, 204, 113, 0.1)',
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    stepSize: 1
                                },
                                title: {
                                    display: true,
                                    text: '回数'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '日付'
                                }
                            }
                        }
                    }
                });
            }

            // 日別散水時間チャート
            const dailyDurationCtx = document.getElementById('dailyDurationChart');
            if (dailyDurationCtx && chartData.daily && chartData.daily.labels.length > 0) {
                new Chart(dailyDurationCtx, {
                    type: 'bar',
                    data: {
                        labels: chartData.daily.labels,
                        datasets: [{
                            label: '散水時間 (分)',
                            data: chartData.daily.durations,
                            backgroundColor: 'rgba(241, 196, 15, 0.7)',
                            borderColor: 'rgba(241, 196, 15, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: '時間 (分)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '日付'
                                }
                            }
                        }
                    }
                });
            }
        }

        function generateWeeklyCharts() {
            // 週別散水量チャート
            const weeklyVolumeCtx = document.getElementById('weeklyVolumeChart');
            if (weeklyVolumeCtx && chartData.weekly && chartData.weekly.labels.length > 0) {
                new Chart(weeklyVolumeCtx, {
                    type: 'bar',
                    data: {
                        labels: chartData.weekly.labels,
                        datasets: [{
                            label: '散水量 (L)',
                            data: chartData.weekly.volumes,
                            backgroundColor: 'rgba(155, 89, 182, 0.7)',
                            borderColor: 'rgba(155, 89, 182, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: '散水量 (リットル)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '週'
                                }
                            }
                        }
                    }
                });
            }

            // 週別散水回数チャート
            const weeklyCountCtx = document.getElementById('weeklyCountChart');
            if (weeklyCountCtx && chartData.weekly && chartData.weekly.labels.length > 0) {
                new Chart(weeklyCountCtx, {
                    type: 'line',
                    data: {
                        labels: chartData.weekly.labels,
                        datasets: [{
                            label: '散水回数',
                            data: chartData.weekly.counts,
                            borderColor: 'rgba(52, 73, 94, 1)',
                            backgroundColor: 'rgba(52, 73, 94, 0.1)',
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: '回数'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '週'
                                }
                            }
                        }
                    }
                });
            }

            // 週別散水時間チャート
            const weeklyDurationCtx = document.getElementById('weeklyDurationChart');
            if (weeklyDurationCtx && chartData.weekly && chartData.weekly.labels.length > 0) {
                new Chart(weeklyDurationCtx, {
                    type: 'bar',
                    data: {
                        labels: chartData.weekly.labels,
                        datasets: [{
                            label: '散水時間 (分)',
                            data: chartData.weekly.durations,
                            backgroundColor: 'rgba(230, 126, 34, 0.7)',
                            borderColor: 'rgba(230, 126, 34, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: '時間 (分)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '週'
                                }
                            }
                        }
                    }
                });
            }

            // 週別手動散水回数チャート
            const weeklyManualCtx = document.getElementById('weeklyManualChart');
            if (weeklyManualCtx && chartData.weekly && chartData.weekly.labels.length > 0) {
                new Chart(weeklyManualCtx, {
                    type: 'bar',
                    data: {
                        labels: chartData.weekly.labels,
                        datasets: [{
                            label: '手動散水回数',
                            data: chartData.weekly.manual_counts,
                            backgroundColor: 'rgba(231, 76, 60, 0.7)',
                            borderColor: 'rgba(231, 76, 60, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    stepSize: 1
                                },
                                title: {
                                    display: true,
                                    text: '回数'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '週'
                                }
                            }
                        }
                    }
                });
            }
        }

        function generateFlowChart() {
            // 流量チャート
            const flowRateCtx = document.getElementById('flowRateChart');
            if (flowRateCtx && chartData.flow && chartData.flow.rates.length > 0) {
                new Chart(flowRateCtx, {
                    type: 'scatter',
                    data: {
                        datasets: [{
                            label: '流量 (L/秒)',
                            data: chartData.flow.rates.map((rate, index) => ({
                                x: index,
                                y: rate
                            })),
                            backgroundColor: 'rgba(52, 152, 219, 0.7)',
                            borderColor: 'rgba(52, 152, 219, 1)',
                            pointRadius: 4,
                            pointHoverRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: '流量 (L/秒)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '散水イベント'
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        return '流量: ' + context.parsed.y.toFixed(3) + ' L/秒';
                                    }
                                }
                            }
                        }
                    }
                });
            }
        }
    """