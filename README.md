# rasp-water

Raspberry Pi を使って自動的に水やりをするシステムです。

## 機能

-   スマホやパソコンから蛇口の開閉が行えます。
-   水流量がリアルタイムに確認できます。
-   スケジュール機能を使って自動水やりが行えます。
-   水やりの記録が確認できます。

## 構成

Angular で作られた UI と，Flask で作られたアプリケーションサーバで構成
されます。raspi-lgpio を使って GPIO を制御し，その先につながった電磁弁
で蛇口の開閉を行います。

ハード関係は[ブログ](https://rabbit-note.com/2018/12/31/raspberry-pi-watering-system-hard/)で紹介しています。

## デモ

下記で，擬似的に水やりを行えます。

https://rasp-water-demo.kubernetes.green-rabbit.net/rasp-water/

## スクリーンショット

<img src="screenshot.png" width="777">

## 設定

同封されている `config.example.yaml` を `config.yaml` に名前変更して，お手元の環境に合わせて書き換えてください。

## 準備

#### パッケージのインストール

```bash:bash
sudo apt install npm docker
```

### ADS1015 のドライバの有効化

/boot/config.txt に次の行を追加。

```bash:bash
dtoverlay=ads1015,cha_gain=0
```

## 実行 (Docker 使用)

```bash:bash
npm ci
npm run build

docker compose run --build --rm --publish 5000:5000 rasp-water
```

## 実行 (Docker 不使用)

[Rye](https://rye.astral.sh/) がインストールされた環境であれば，
下記のようにして Docker を使わずに実行できます．

```bash:bash
rye sync
rye run python flask/src/app.py
```

## Kubernetes で動かす場合

Kubernetes で実行するため設定ファイルが `kubernetes/rasp-water.yaml` に入っていますので，
適宜カスタマイズして使っていただければと思います。

## カスタマイズ

電磁弁の制御は `flask/src/rasp_water/valve.py` の `{set,get}\_state` で行っていますの
で，ここを書き換えることで制御方法を変えることができます。

## テスト結果

-   https://kimata.github.io/rasp-water/
-   https://kimata.github.io/rasp-water/coverage/

# ライセンス

Apache License Version 2.0 を適用します。
