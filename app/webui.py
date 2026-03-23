from __future__ import annotations

import argparse
import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extractor import (
    DEFAULT_SPEAKER_NAME,
    ExtractionError,
    extract_from_source,
    render_html,
    render_markdown,
    render_text,
)
from app.search import SearchResult, search_documents_by_speaker


APP_TITLE = "都議会発言抽出ツール"
SPEAKER_SUGGESTIONS = ("さんのへあや", "上田令子")
DEFAULT_SEARCH_FILTER = ""
DEFAULT_SEARCH_PAGES = 3


def build_result_payload(source: str, mode: str, speaker_name: str) -> dict[str, str]:
    extracted = extract_from_source(source, mode=mode, target_speaker=speaker_name)
    return {
        "title": extracted.title,
        "date_iso": extracted.date_iso,
        "meeting_name": extracted.meeting_name,
        "category": extracted.category,
        "speaker_name": extracted.target_speaker,
        "html": render_html(extracted.blocks),
        "markdown": render_markdown(extracted.blocks),
        "text": render_text(extracted.blocks),
    }


def render_page(
    *,
    source: str = "",
    mode: str = "full",
    speaker_name: str = DEFAULT_SPEAKER_NAME,
    result: dict[str, str] | None = None,
    error: str = "",
    search_filter: str = DEFAULT_SEARCH_FILTER,
    search_pages: int = DEFAULT_SEARCH_PAGES,
    search_results: list[SearchResult] | None = None,
    search_error: str = "",
) -> str:
    source_value = html.escape(source, quote=True)
    speaker_value = html.escape(speaker_name, quote=True)
    search_filter_value = html.escape(search_filter, quote=True)
    error_html = (
        f'<div class="notice notice-error">{html.escape(error)}</div>' if error else ""
    )
    search_error_html = (
        f'<div class="notice notice-error">{html.escape(search_error)}</div>'
        if search_error
        else ""
    )
    result_html = render_result_section(result) if result else ""
    search_html = render_search_section(
        speaker_name=speaker_name,
        search_filter=search_filter,
        search_pages=search_pages,
        search_results=search_results,
        mode=mode,
    )

    full_checked = "checked" if mode == "full" else ""
    self_checked = "checked" if mode == "self" else ""

    search_pages_options = "".join(
        render_option(value, search_pages)
        for value in (1, 3, 5)
    )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    :root {{
      --bg: #f3f0e8;
      --surface: #fffdf9;
      --ink: #1f2a37;
      --muted: #6b7280;
      --accent: #155e75;
      --accent-strong: #0f4c5c;
      --line: #d6d3d1;
      --error-bg: #fff1f2;
      --error-line: #e11d48;
      --shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Hiragino Sans", "Yu Gothic", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(21, 94, 117, 0.15), transparent 28rem),
        linear-gradient(180deg, #efe7db 0%, var(--bg) 42%, #ebe7de 100%);
    }}
    .page {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 40px 20px 64px;
    }}
    .hero {{
      margin-bottom: 24px;
    }}
    .eyebrow {{
      display: inline-block;
      margin-bottom: 12px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(21, 94, 117, 0.1);
      color: var(--accent-strong);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(32px, 5vw, 52px);
      line-height: 1.05;
      font-family: "Hiragino Mincho ProN", "Yu Mincho", serif;
      font-weight: 700;
    }}
    .home-link {{
      color: inherit;
      text-decoration: none;
    }}
    .home-link:hover {{
      color: var(--accent-strong);
    }}
    .lead {{
      margin: 0;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.7;
      max-width: 54rem;
    }}
    .card {{
      background: rgba(255, 253, 249, 0.95);
      border: 1px solid rgba(214, 211, 209, 0.9);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(6px);
    }}
    .form-card {{
      padding: 24px;
      margin-bottom: 20px;
    }}
    .form-grid {{
      display: grid;
      gap: 18px;
    }}
    .two-col {{
      display: grid;
      gap: 18px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    label {{
      display: block;
      margin-bottom: 8px;
      font-weight: 700;
      font-size: 14px;
    }}
    input[type="text"], select {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 15px;
    }}
    .radio-row {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .radio-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      font-size: 14px;
    }}
    .actions {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      padding: 12px 18px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{
      background: #e7e5e4;
      color: var(--ink);
    }}
    .hint {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    .notice {{
      margin-bottom: 18px;
      padding: 14px 16px;
      border-radius: 14px;
      font-size: 14px;
      line-height: 1.6;
    }}
    .notice-error {{
      background: var(--error-bg);
      border: 1px solid rgba(225, 29, 72, 0.3);
      color: #9f1239;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .meta-item {{
      padding: 16px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(214, 211, 209, 0.85);
    }}
    .meta-label {{
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .meta-value {{
      font-size: 18px;
      line-height: 1.45;
      word-break: break-word;
    }}
    .result-card {{
      padding: 24px;
    }}
    .result-grid {{
      display: grid;
      gap: 18px;
    }}
    .result-panel {{
      padding: 18px;
      border-radius: 18px;
      border: 1px solid rgba(214, 211, 209, 0.85);
      background: rgba(255,255,255,0.8);
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .panel-header h2 {{
      margin: 0;
      font-size: 18px;
    }}
    textarea {{
      width: 100%;
      min-height: 220px;
      padding: 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 14px;
      line-height: 1.7;
      resize: vertical;
    }}
    .search-list {{
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }}
    .search-item {{
      display: grid;
      gap: 10px;
      padding: 16px;
      border-radius: 18px;
      border: 1px solid rgba(214, 211, 209, 0.85);
      background: rgba(255,255,255,0.8);
    }}
    .search-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      align-items: baseline;
    }}
    .search-title {{
      font-size: 18px;
      line-height: 1.5;
      margin: 0;
      font-weight: 700;
    }}
    .search-meta {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    .search-actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .inline-form {{
      margin: 0;
    }}
    .search-link {{
      color: var(--accent-strong);
      font-size: 14px;
      text-decoration: none;
      font-weight: 700;
    }}
    .footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    @media (max-width: 720px) {{
      .page {{
        padding: 24px 14px 48px;
      }}
      .form-card, .result-card {{
        padding: 18px;
      }}
      .two-col {{
        grid-template-columns: 1fr;
      }}
      .panel-header, .search-top {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .actions {{
        width: 100%;
      }}
      button {{
        width: 100%;
      }}
      .search-actions {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="eyebrow">Tokyo Metropolitan Assembly Record Helper</div>
      <h1><a class="home-link" href="/">{APP_TITLE}</a></h1>
      <p class="lead">発言者名を選んで会議録候補を一覧から選ぶか、本文 URL を直接貼り付けるだけで、WordPress 用 HTML をすぐに作れます。</p>
    </section>
    <section class="card form-card">
      {search_error_html}
      <form method="post" action="/search" class="form-grid">
        <div class="two-col">
          <div>
            <label for="search-speaker-name">発言者名</label>
            <input id="search-speaker-name" list="speaker-suggestions" type="text" name="speaker_name" value="{speaker_value}" placeholder="さんのへあや" required>
          </div>
          <div>
            <label for="search-filter">文書名の絞り込み</label>
            <input id="search-filter" type="text" name="search_filter" value="{search_filter_value}" placeholder="例: 厚生 / 予算特別 / 2025-03-18">
          </div>
        </div>
        <div class="two-col">
          <div>
            <label for="search-pages">候補取得ページ数</label>
            <select id="search-pages" name="search_pages">{search_pages_options}</select>
          </div>
          <div>
            <label>抽出モード</label>
            <div class="radio-row">
              <label class="radio-pill"><input type="radio" name="mode" value="full" {full_checked}> 質疑全文</label>
              <label class="radio-pill"><input type="radio" name="mode" value="self" {self_checked}> 本人発言のみ</label>
            </div>
          </div>
        </div>
        <div class="actions">
          <button type="submit">候補一覧を出す</button>
          <span class="hint">選んだ発言者の会議録候補を最新順で取得します。まずここから選ぶと `Id=...` を手で探さずに済みます。</span>
        </div>
      </form>
      {search_html}
    </section>
    <section class="card form-card">
      {error_html}
      <form method="post" action="/extract" class="form-grid">
        <div class="two-col">
          <div>
            <label for="speaker-name">抽出対象の発言者名</label>
            <input id="speaker-name" list="speaker-suggestions" type="text" name="speaker_name" value="{speaker_value}" placeholder="さんのへあや" required>
          </div>
          <div>
            <label for="source">会議録 URL またはローカル HTML ファイル</label>
            <input id="source" type="text" name="source" value="{source_value}" placeholder="https://www.record.gikai.metro.tokyo.lg.jp/100000?Template=document&amp;Id=19672" required>
          </div>
        </div>
        <div>
          <label>抽出モード</label>
          <div class="radio-row">
            <label class="radio-pill"><input type="radio" name="mode" value="full" {full_checked}> 質疑全文</label>
            <label class="radio-pill"><input type="radio" name="mode" value="self" {self_checked}> 本人発言のみ</label>
          </div>
        </div>
        <div class="actions">
          <button type="submit">抽出する</button>
          <button type="button" class="secondary" onclick="fillSample()">サンプルを入れる</button>
          <span class="hint">例: さんのへあや / 上田令子。確認用 URL は `Id=19672` です。</span>
        </div>
      </form>
    </section>
    {result_html}
    <div class="footer">
      ローカル PC 上で動かす前提です。公開サーバーではなく、事務所の作業用ブラウザから使う想定にしています。
    </div>
  </main>
  <datalist id="speaker-suggestions">
    {render_speaker_suggestions()}
  </datalist>
  <script>
    function copyText(id) {{
      const target = document.getElementById(id);
      target.select();
      target.setSelectionRange(0, target.value.length);
      navigator.clipboard.writeText(target.value).then(() => {{
        const button = document.querySelector('[data-copy-target="' + id + '"]');
        const original = button.textContent;
        button.textContent = 'コピーしました';
        setTimeout(() => {{ button.textContent = original; }}, 1200);
      }});
    }}
    function fillSample() {{
      document.getElementById('speaker-name').value = 'さんのへあや';
      document.getElementById('search-speaker-name').value = 'さんのへあや';
      document.getElementById('source').value = 'https://www.record.gikai.metro.tokyo.lg.jp/100000?Template=document&Id=19672';
    }}
  </script>
</body>
</html>
"""


def render_speaker_suggestions() -> str:
    return "\n".join(
        f'<option value="{html.escape(name, quote=True)}"></option>'
        for name in SPEAKER_SUGGESTIONS
    )


def render_option(value: int, selected: int) -> str:
    selected_attr = " selected" if value == selected else ""
    return f'<option value="{value}"{selected_attr}>最新{value * 10}件程度</option>'


def render_search_section(
    *,
    speaker_name: str,
    search_filter: str,
    search_pages: int,
    search_results: list[SearchResult] | None,
    mode: str,
) -> str:
    if search_results is None:
        return ""

    heading = f"{html.escape(speaker_name)} の候補文書"
    filter_line = (
        f'絞り込み: {html.escape(search_filter)}'
        if search_filter
        else "絞り込みなし"
    )

    if not search_results:
        return f"""
        <section class="search-list">
          <div class="search-item">
            <div class="search-title">{heading}</div>
            <div class="search-meta">取得範囲: 最新{search_pages * 10}件程度 / {filter_line}</div>
            <div class="hint">条件に合う文書は見つかりませんでした。</div>
          </div>
        </section>
        """

    items_html = "".join(
        render_search_item(result, speaker_name=speaker_name, mode=mode)
        for result in search_results
    )
    return f"""
    <section class="search-list">
      <div class="search-item">
        <div class="search-title">{heading}</div>
        <div class="search-meta">取得件数: {len(search_results)}件 / 取得範囲: 最新{search_pages * 10}件程度 / {filter_line}</div>
      </div>
      {items_html}
    </section>
    """


def render_search_item(result: SearchResult, *, speaker_name: str, mode: str) -> str:
    title = html.escape(result.title)
    date_iso = html.escape(result.date_iso)
    url = html.escape(result.url, quote=True)
    speaker = html.escape(speaker_name, quote=True)
    mode_value = html.escape(mode, quote=True)
    hit_count = result.hit_count
    return f"""
    <article class="search-item">
      <div class="search-top">
        <h2 class="search-title">{title}</h2>
        <div class="search-meta">{date_iso} / {hit_count} 発言ヒット</div>
      </div>
      <div class="search-actions">
        <form class="inline-form" method="post" action="/extract">
          <input type="hidden" name="speaker_name" value="{speaker}">
          <input type="hidden" name="source" value="{url}">
          <input type="hidden" name="mode" value="{mode_value}">
          <button type="submit">この文書で抽出</button>
        </form>
        <a class="search-link" href="{url}" target="_blank" rel="noreferrer">公式ページを開く</a>
      </div>
    </article>
    """


def render_result_section(result: dict[str, str]) -> str:
    title = html.escape(result["title"])
    date_iso = html.escape(result["date_iso"])
    meeting_name = html.escape(result["meeting_name"])
    category = html.escape(result["category"])
    speaker_name = html.escape(result["speaker_name"])
    html_output = html.escape(result["html"])
    markdown_output = html.escape(result["markdown"])
    text_output = html.escape(result["text"])

    return f"""
    <section class="card result-card">
      <div class="meta">
        <div class="meta-item"><span class="meta-label">タイトル</span><div class="meta-value">{title}</div></div>
        <div class="meta-item"><span class="meta-label">日付</span><div class="meta-value">{date_iso}</div></div>
        <div class="meta-item"><span class="meta-label">会議名</span><div class="meta-value">{meeting_name}</div></div>
        <div class="meta-item"><span class="meta-label">カテゴリ候補</span><div class="meta-value">{category}</div></div>
        <div class="meta-item"><span class="meta-label">発言者</span><div class="meta-value">{speaker_name}</div></div>
      </div>
      <div class="result-grid">
        {render_output_panel("WordPress 用 HTML", "html-output", html_output)}
        {render_output_panel("Markdown", "markdown-output", markdown_output)}
        {render_output_panel("プレーンテキスト", "text-output", text_output)}
      </div>
    </section>
    """


def render_output_panel(title: str, element_id: str, value: str) -> str:
    return f"""
    <section class="result-panel">
      <div class="panel-header">
        <h2>{html.escape(title)}</h2>
        <button type="button" data-copy-target="{element_id}" onclick="copyText('{element_id}')">コピー</button>
      </div>
      <textarea id="{element_id}" readonly>{value}</textarea>
    </section>
    """


class ExtractorHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.respond_html(render_page())

    def do_POST(self) -> None:  # noqa: N802
        form_data = self.read_form_data()
        source = form_data.get("source", "").strip()
        mode = normalized_mode(form_data.get("mode", "full"))
        speaker_name = form_data.get("speaker_name", DEFAULT_SPEAKER_NAME).strip() or DEFAULT_SPEAKER_NAME
        search_filter = form_data.get("search_filter", "").strip()
        search_pages = parse_search_pages(form_data.get("search_pages", str(DEFAULT_SEARCH_PAGES)))

        if self.path == "/extract":
            try:
                result = build_result_payload(
                    source=source,
                    mode=mode,
                    speaker_name=speaker_name,
                )
                page = render_page(
                    source=source,
                    mode=mode,
                    speaker_name=speaker_name,
                    result=result,
                    search_filter=search_filter,
                    search_pages=search_pages,
                )
            except ExtractionError as exc:
                page = render_page(
                    source=source,
                    mode=mode,
                    speaker_name=speaker_name,
                    error=str(exc),
                    search_filter=search_filter,
                    search_pages=search_pages,
                )
            self.respond_html(page)
            return

        if self.path == "/search":
            try:
                _, results = search_documents_by_speaker(
                    speaker_name=speaker_name,
                    max_pages=search_pages,
                    title_filter=search_filter,
                )
                page = render_page(
                    source=source,
                    mode=mode,
                    speaker_name=speaker_name,
                    search_filter=search_filter,
                    search_pages=search_pages,
                    search_results=results,
                )
            except ExtractionError as exc:
                page = render_page(
                    source=source,
                    mode=mode,
                    speaker_name=speaker_name,
                    search_filter=search_filter,
                    search_pages=search_pages,
                    search_error=str(exc),
                )
            self.respond_html(page)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def read_form_data(self) -> dict[str, str]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        parsed = parse_qs(raw_body, keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items()}

    def respond_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def normalized_mode(mode: str) -> str:
    if mode not in {"full", "self"}:
        return "full"
    return mode


def parse_search_pages(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_SEARCH_PAGES
    return max(1, min(parsed, 5))


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="発言抽出ツールのローカル Web UI")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="待受ホスト",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8765")),
        help="待受ポート",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ExtractorHTTPRequestHandler)
    print(f"http://{args.host}:{args.port} で起動しました")
    print("Ctrl+C で終了します")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
