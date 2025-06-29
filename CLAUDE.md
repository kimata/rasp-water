# CLAUDE.md

このファイルは Claude Code (claude.ai/code) がこのリポジトリで作業する際のガイダンスを提供します。

## プロジェクト概要

これは Raspberry Pi 自動水やりシステム（"rasp-water"）で、以下のアーキテクチャを持ちます：

- **フロントエンド**: `src/` 内の Angular 20 アプリケーション（TypeScript/SCSS）
- **バックエンド**: `flask/src/` 内の Flask アプリケーション（Python）
- **ハードウェア制御**: rpi-lgpio を使用して電磁弁の GPIO ピンを制御
- **データストレージ**: ログとスケジューリング用の SQLite データベース
- **外部連携**: 天気予報、Slack通知、InfluxDBメトリクス

## 主要コンポーネント

### フロントエンド（Angular）

- 主要コンポーネント: `valve-control`, `scheduler-control`, `log`, `header`, `footer`, `toast`
- サービス: 通知用の `push.service`, `toast.service`
- UIは Bootstrap 5 と ng-bootstrap で構築
- 日時選択に tempus-dominus、アイコンに FontAwesome を使用

### バックエンド（Flask）

- エントリーポイント: `flask/src/app.py` - blueprint登録を持つメインFlaskサーバー
- `flask/src/rasp_water/` 内の主要モジュール:
    - `valve.py` - 電磁弁制御（{set,get}\_state メソッドをここでカスタマイズ）
    - `scheduler.py` - 天気連携付き自動水やりスケジュール
    - `weather_forecast.py` - 雨予報用Yahoo天気API連携
    - `weather_sensor.py` - 雨センサーデータ収集
    - `webapp_*.py` - バルブとスケジュール制御用Web APIエンドポイント
- 共通的なWebアプリユーティリティ、ログ、設定用のmy-lib依存関係を使用

## 開発コマンド

### フロントエンド（Angular）

```bash
# 依存関係のインストール
npm ci

# 開発サーバー（全インターフェースでアクセス可能）
npm start

# 本番ビルド
npm run build

# テスト実行
npm test

# 開発中のウォッチモード
npm run watch

# TypeScriptファイルのリント（手動ESLint実行）
npx eslint 'src/**/*.{ts,tsx}'
```

### バックエンド（Python）

```bash
# uv使用（推奨）
uv sync
uv run python flask/src/app.py

# Rye使用（代替）
rye sync
rye run python flask/src/app.py

# pip使用（フォールバック）
pip install -r requirements.lock
python flask/src/app.py

# デバッグモードで実行
uv run python flask/src/app.py -D

# ダミーモードで実行（ハードウェアなしでのテスト）
uv run python flask/src/app.py -d
```

### テスト

```bash
# カバレッジ付きPythonテスト実行
uv run pytest

# 単一テストファイル実行
uv run pytest tests/test_basic.py

# Playwrightテスト実行（エンドツーエンドブラウザテスト）
uv run pytest tests/test_playwright.py

# テストはHTMLレポートを tests/evidence/index.htm に生成
# カバレッジレポートは tests/evidence/coverage/ に生成
# Playwrightテスト録画は tests/evidence/test_*/ に保存
```

### Docker デプロイ

```bash
# フルビルドと実行
npm ci && npm run build
docker compose run --build --rm --publish 5000:5000 rasp-water
```

## 設定

- `config.example.yaml` を `config.yaml` にコピーしてカスタマイズ
- Flask アプリはデフォルトでポート5000で動作
- Angular ビルドは `/rasp-water/` ベースhrefで `dist/rasp-water/browser/` に出力
- 設定にはGPIOピン設定、センサーキャリブレーション、天気APIキーが含まれる
- InfluxDB、Slack、天気サービス連携をサポート

## ハードウェア統合

- rpi-lgpio ライブラリによる GPIO 制御（非推奨の RPi.GPIO を置き換え）
- アナログセンサー用に `/dev/gpiomem` アクセスと ADS1015 オーバーレイが必要
- IIOインターフェース経由での流量測定用ADS1015 ADC
- バルブ制御ロジックは `flask/src/rasp_water/valve.py` にある
- センサーデータ収集は流量モニタリングとエラー検出を処理

## 理解すべき主要ファイル

- `flask/src/app.py` - blueprint登録を持つFlaskアプリケーションファクトリー
- `src/app/app.component.ts` - Angular ルートコンポーネント
- `config.yaml` - ハードウェア、API、連携用ランタイム設定
- `compose.yaml` - ハードウェアデバイスアクセス付きDocker デプロイ
- `pyproject.toml` - Python 依存関係管理とテスト設定