# ToGikai Record Downloader

東京都議会会議録から、指定した議員の発言を抽出して、
WordPress 貼り付け用 HTML / Markdown / プレーンテキストを生成するツールです。

現状は次に対応しています。

- 発言者指定
  - `さんのへあや`
  - `上田令子`
  - そのほか任意入力
- 抽出モード
  - `質疑全文`
  - `本人発言のみ`
- 利用方法
  - 会議録本文 URL を直接指定
  - 発言者名から候補文書を検索して選択
- 出力形式
  - WordPress 用 HTML
  - Markdown
  - プレーンテキスト

## ローカル起動

依存ライブラリは使っていません。Python 標準ライブラリだけで動きます。

### Web UI

```bash
python3 app/webui.py
```

ブラウザで次を開きます。

```text
http://127.0.0.1:8765
```

### CLI

```bash
python3 app/extractor.py "https://www.record.gikai.metro.tokyo.lg.jp/100000?Template=document&Id=19672" --speaker さんのへあや --mode full --format html --body-only
```

```bash
python3 app/extractor.py "https://www.record.gikai.metro.tokyo.lg.jp/488333?Template=document&Id=19962" --speaker 上田令子 --mode self --format text --body-only
```

## テスト

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Render デプロイ

Render 用の設定ファイルは [render.yaml](/Users/kikutakenji/Python/ToGikai-record-downloader/render.yaml) です。

手順は [docs/render-deploy.md](/Users/kikutakenji/Python/ToGikai-record-downloader/docs/render-deploy.md) にあります。

概要だけ書くと次です。

1. このリポジトリを GitHub に push
2. Render で `Blueprint` を作成
3. `render.yaml` を読み込ませる
4. 発行された `onrender.com` URL を共有

## 補足

- Web UI の候補一覧は、東京都議会サイトの発言者検索を利用して取得します
- 公開 URL をそのまま使う構成です
- 現時点ではパスワード保護は入れていません
