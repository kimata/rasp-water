# 🌱 rasp-water

Raspberry Pi を使った自動水やりシステム

[![Regression](https://github.com/kimata/rasp-water/actions/workflows/regression.yaml/badge.svg)](https://github.com/kimata/rasp-water/actions/workflows/regression.yaml)

## 📑 目次

- [📋 概要](#-概要)
  - [主な特徴](#主な特徴)
- [🖼️ スクリーンショット](#️-スクリーンショット)
- [🎮 デモ](#-デモ)
- [🏗️ システム構成](#️-システム構成)
  - [フロントエンド](#フロントエンド)
  - [バックエンド](#バックエンド)
  - [ハードウェア](#ハードウェア)
- [🚀 セットアップ](#-セットアップ)
  - [必要な環境](#必要な環境)
  - [1. 依存パッケージのインストール](#1-依存パッケージのインストール)
  - [2. ハードウェア設定](#2-ハードウェア設定)
  - [3. 設定ファイルの準備](#3-設定ファイルの準備)
- [💻 実行方法](#-実行方法)
  - [Docker を使用する場合（推奨）](#docker-を使用する場合推奨)
  - [Docker を使用しない場合](#docker-を使用しない場合)
  - [開発モード](#開発モード)
- [🧪 テスト](#-テスト)
- [🎯 API エンドポイント](#-api-エンドポイント)
  - [バルブ制御](#バルブ制御)
  - [スケジュール管理](#スケジュール管理)
  - [ログ・履歴](#ログ履歴)
  - [メトリクス](#メトリクス)
- [☸️ Kubernetes デプロイ](#️-kubernetes-デプロイ)
- [🔧 カスタマイズ](#-カスタマイズ)
  - [バルブ制御のカスタマイズ](#バルブ制御のカスタマイズ)
  - [フロントエンドのカスタマイズ](#フロントエンドのカスタマイズ)
- [📊 CI/CD](#-cicd)
- [📝 ライセンス](#-ライセンス)

## 📋 概要

Raspberry Pi と電磁弁を使って、植物への水やりを自動化するシステムです。スマートフォンやPCから遠隔操作でき、スケジュール機能による完全自動化も可能です。

### 主な特徴

- 🌸 **リモート制御** - スマホやPCから蛇口の開閉操作
- 💧 **流量監視** - リアルタイムでの水流量確認
- ⏰ **スケジュール機能** - 時間指定での自動水やり
- 🌤️ **天気連動** - 雨予報時の自動キャンセル機能
- 📊 **履歴管理** - 水やり記録の保存と確認
- 📱 **通知機能** - Slack連携によるアラート通知
- 📈 **メトリクス** - InfluxDBへのデータ送信対応

## 🖼️ スクリーンショット

<img src="screenshot.png" width="388" alt="rasp-water UI">

## 🎮 デモ

実際の動作を体験できるデモサイト：

🔗 https://rasp-water-demo.kubernetes.green-rabbit.net/rasp-water/

## 🏗️ システム構成

### フロントエンド

- **フレームワーク**: Angular 19
- **UIライブラリ**: Bootstrap 5 + ng-bootstrap
- **アイコン**: FontAwesome
- **日時選択**: Tempus Dominus

### バックエンド

- **フレームワーク**: Flask (Python)
- **GPIO制御**: rpi-lgpio
- **データベース**: SQLite
- **タスクスケジューラ**: Python schedule

### ハードウェア

- **制御**: Raspberry Pi + 電磁弁
- **センサー**: ADS1015 ADC (流量測定用)
- **詳細**: [ハードウェア構成の詳細はブログ参照](https://rabbit-note.com/2018/12/31/raspberry-pi-watering-system-hard/)

## 🚀 セットアップ

### 必要な環境

- Raspberry Pi (GPIO制御が可能なモデル)
- Python 3.10+
- Node.js 22.x
- Docker (オプション)

### 1. 依存パッケージのインストール

```bash
# システムパッケージ
sudo apt install npm docker

# プロジェクトの依存関係
npm ci
```

### 2. ハードウェア設定

ADS1015ドライバを有効化するため、`/boot/config.txt` に以下を追加：

```
dtoverlay=ads1015,cha_gain=0
```

### 3. 設定ファイルの準備

```bash
cp config.example.yaml config.yaml
# config.yaml を環境に合わせて編集
```

設定項目の例：

- GPIO ピン番号
- センサーのキャリブレーション値
- 天気予報API設定
- Slack/InfluxDB連携設定

## 💻 実行方法

### Docker を使用する場合（推奨）

```bash
# フロントエンドのビルド
npm ci
npm run build

# Docker Composeで起動
docker compose run --build --rm --publish 5000:5000 rasp-water
```

### Docker を使用しない場合

#### uv を使用（推奨）

```bash
# uvのインストール（未インストールの場合）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 依存関係のインストールと実行
uv sync
uv run python flask/src/app.py
```

#### Rye を使用（代替）

```bash
# Ryeのインストール（未インストールの場合）
curl -sSf https://rye.astral.sh/get | bash

# 依存関係のインストールと実行
rye sync
rye run python flask/src/app.py
```

### 開発モード

```bash
# フロントエンド開発サーバー
npm start

# バックエンド（デバッグモード）
uv run python flask/src/app.py -D

# ダミーモード（ハードウェアなしでテスト）
uv run python flask/src/app.py -d
```

## 🧪 テスト

```bash
# Pythonテスト（カバレッジ付き）
uv run pytest

# 特定のテストファイルを実行
uv run pytest tests/test_basic.py

# E2Eテスト（Playwright）
uv run pytest tests/test_playwright.py
```

テスト結果：

- HTMLレポート: `tests/evidence/index.htm`
- カバレッジ: `tests/evidence/coverage/`
- E2E録画: `tests/evidence/test_*/`

## 🎯 API エンドポイント

### バルブ制御

- `GET /api/valve_ctrl` - バルブ状態取得
- `POST /api/valve_ctrl` - バルブ開閉制御

### スケジュール管理

- `GET /api/schedule_ctrl` - スケジュール一覧取得
- `POST /api/schedule_ctrl` - スケジュール追加/更新
- `DELETE /api/schedule_ctrl/<id>` - スケジュール削除

### ログ・履歴

- `GET /api/log` - 水やり履歴取得

### メトリクス

- `GET /api/metrics` - メトリクスダッシュボード（HTML形式）

メトリクス機能では以下のデータを自動収集・記録します：

**水やりメトリクス（`watering_metrics`テーブル）**：
- 水やり操作種別（`manual` / `auto`）
- 散水時間（秒単位）
- 散水量（リットル単位）
- 実行日時

**エラーメトリクス（`error_metrics`テーブル）**：
- エラー種別（`valve_control`, `schedule`, `sensor`等）
- エラーメッセージ
- 発生日時

**ダッシュボード機能**：
- Chart.js による対話的グラフ表示
- 過去30日間の統計サマリー（総回数、手動/自動別、散水量・時間、エラー数）
- 日別・週別時系列分析（散水量・回数・時間の推移）
- 流量分析（リットル/秒）
- Bulma CSS によるレスポンシブデザイン
- パーマリンク機能（セクション別URL）

## ☸️ Kubernetes デプロイ

Kubernetes用の設定ファイルが含まれています：

```bash
kubectl apply -f kubernetes/rasp-water.yaml
```

詳細は設定ファイルをカスタマイズしてご利用ください。

## 🔧 カスタマイズ

### バルブ制御のカスタマイズ

電磁弁の制御ロジックは `flask/src/rasp_water/valve.py` の `set_state()` / `get_state()` メソッドで実装されています。異なるハードウェア構成に対応する場合は、これらのメソッドを修正してください。

### フロントエンドのカスタマイズ

- コンポーネント: `src/app/` 配下
- スタイル: 各コンポーネントの `.scss` ファイル

## 📊 CI/CD

GitHub Actions によるCI/CDパイプライン：

- テスト結果: https://kimata.github.io/rasp-water/
- カバレッジレポート: https://kimata.github.io/rasp-water/coverage/

## 📝 ライセンス

このプロジェクトは Apache License Version 2.0 のもとで公開されています。

---

<div align="center">

**⭐ このプロジェクトが役に立った場合は、Star をお願いします！**

[🐛 Issue 報告](https://github.com/kimata/rasp-water/issues) | [💡 Feature Request](https://github.com/kimata/rasp-water/issues/new?template=feature_request.md) | [📖 Wiki](https://github.com/kimata/rasp-water/wiki)

</div>
