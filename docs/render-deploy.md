# Render デプロイ手順

このリポジトリには [render.yaml](/Users/kikutakenji/Python/ToGikai-record-downloader/render.yaml) を追加済み。
Render Blueprint を使えば、そのまま Web Service として作成できる。

## 1. 前提

- GitHub などにこのリポジトリを push しておく
- Render アカウントを用意する

## 2. 作成手順

1. Render にログイン
2. `New +` から `Blueprint` を選ぶ
3. このリポジトリを接続する
4. `render.yaml` を読み込ませる
5. 内容を確認して作成する

作成される設定:

- Service type: `web`
- Runtime: `python`
- Region: `singapore`
- Plan: `free`
- Build command: `python3 -m compileall app`
- Start command: `python3 app/webui.py`

## 3. 公開 URL

デプロイ後、Render が `onrender.com` の URL を発行する。

この URL を本人確認用に共有すればよい。

## 4. 注意

- Render の Web Service は公開 URL になる
- 現状のアプリにはログイン制御を入れていない
- 本人だけに見せたいなら、次の段階で簡易パスワード認証を追加した方がよい

## 5. ローカルとの違い

ローカル:

```bash
python3 app/webui.py
```

Render:

- `HOST=0.0.0.0`
- `PORT` は Render 側の環境変数を利用

これらは `render.yaml` と `app/webui.py` で対応済み。
