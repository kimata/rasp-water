# rasp-water

Raspberry Pi Zero W を使って自動的に水やりをするシステムです．

## 機能

- スマホやパソコンから蛇口の開閉が行えます．
- 水流量がリアルタイムに確認できます．
- スケジュール機能を使って自動水やりが行えます．
- 水やりの記録が確認できます．

## 構成

Angular で作られた UI と，Flask で作られたアプリケーションサーバで構成
されます．raspi-gpio を使って GPIO を制御し，その先につながった電磁弁
で蛇口の開閉を行います．

スケジュール機能は cron ファイルを読み書きして実現しています．

ログ機能は SQLite を使っています．
