from __future__ import annotations

import dataclasses
import html
import re
import subprocess
import tempfile
from pathlib import Path

from app.extractor import (
    ExtractionError,
    clean_inline_text,
    normalize_speaker_name,
    normalize_text,
    validate_supported_speaker,
)


SEARCH_BASE_URL = "https://www.record.gikai.metro.tokyo.lg.jp/100000"
DEFAULT_MAX_PAGES = 3


@dataclasses.dataclass(slots=True)
class SpeakerOption:
    speaker_id: str
    label: str


@dataclasses.dataclass(slots=True)
class SearchResult:
    date_iso: str
    title: str
    url: str
    hit_count: int


def parse_speaker_options(html_text: str) -> list[SpeakerOption]:
    select_match = re.search(
        r'<select[^>]+name="SpeakerName\[\]"[^>]*>(.*?)</select>',
        html_text,
        re.DOTALL,
    )
    if not select_match:
        raise ExtractionError("発言者一覧の取得に失敗しました")

    options_html = select_match.group(1)
    options = []
    for value, label in re.findall(
        r'<option value="([^"]*)"[^>]*>([^<]+)</option>',
        options_html,
    ):
        speaker_id = clean_inline_text(value)
        speaker_label = clean_inline_text(label)
        if not speaker_id or speaker_label == "【指定しない】":
            continue
        options.append(SpeakerOption(speaker_id=speaker_id, label=speaker_label))
    return options


def resolve_speaker_option(
    speaker_name: str,
    options: list[SpeakerOption],
) -> SpeakerOption:
    target_name = validate_supported_speaker(speaker_name)
    target = normalize_speaker_name(target_name)
    exact_matches = [
        option for option in options if normalize_speaker_name(option.label) == target
    ]
    if exact_matches:
        return exact_matches[0]

    partial_matches = [
        option for option in options if target and target in normalize_speaker_name(option.label)
    ]
    if partial_matches:
        return partial_matches[0]

    raise ExtractionError(f"会議録サイトで発言者「{target_name}」が見つかりませんでした")


def parse_csrf_token(html_text: str) -> str:
    match = re.search(r'name="_token" value="([^"]+)"', html_text)
    if not match:
        raise ExtractionError("会議録サイトの検索トークン取得に失敗しました")
    return match.group(1)


def parse_search_results(html_text: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    pattern = re.compile(
        r'<li class="result__item">.*?'
        r'<div class="ans-title__date">([^<]+)</div>.*?'
        r'<div class="ans-title__name">\s*<a href="([^"]+)">([^<]+)</a>.*?'
        r'<strong class="color-red">(\d+)</strong>\s*発言ヒット',
        re.DOTALL,
    )
    for date_iso, url, title, hit_count in pattern.findall(html_text):
        normalized_url = html.unescape(clean_inline_text(url))
        normalized_url = re.sub(r"#.*$", "", normalized_url)
        results.append(
            SearchResult(
                date_iso=clean_inline_text(date_iso),
                title=clean_inline_text(html.unescape(title)),
                url=normalized_url,
                hit_count=int(hit_count),
            )
        )
    return results


def filter_results(results: list[SearchResult], title_filter: str) -> list[SearchResult]:
    title_filter = title_filter.strip()
    if not title_filter:
        return results

    normalized_filter = normalize_text(title_filter)
    filtered = []
    for result in results:
        haystack = normalize_text(f"{result.date_iso} {result.title}")
        if normalized_filter in haystack:
            filtered.append(result)
    return filtered


def search_documents_by_speaker(
    speaker_name: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    title_filter: str = "",
) -> tuple[SpeakerOption, list[SearchResult]]:
    max_pages = max(1, min(max_pages, 5))

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = Path(tmp_dir) / "cookies.txt"
        search_page_html = fetch_search_speaker_page(cookie_path)
        token = parse_csrf_token(search_page_html)
        speaker_option = resolve_speaker_option(
            speaker_name,
            parse_speaker_options(search_page_html),
        )

        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for page in range(1, max_pages + 1):
            page_html = post_speaker_search(
                cookie_path=cookie_path,
                token=token,
                speaker_id=speaker_option.speaker_id,
                page=page,
            )
            page_results = parse_search_results(page_html)
            if not page_results:
                break
            for result in page_results:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)
            if len(page_results) < 10:
                break

    return speaker_option, filter_results(results, title_filter)


def fetch_search_speaker_page(cookie_path: Path) -> str:
    return run_curl(
        [
            "curl",
            "-L",
            "-s",
            "-c",
            str(cookie_path),
            f"{SEARCH_BASE_URL}?Template=search-speaker",
        ]
    )


def post_speaker_search(
    *,
    cookie_path: Path,
    token: str,
    speaker_id: str,
    page: int,
) -> str:
    command = [
        "curl",
        "-L",
        "-s",
        "-b",
        str(cookie_path),
        "-c",
        str(cookie_path),
        "-X",
        "POST",
        SEARCH_BASE_URL,
        "--data-urlencode",
        f"_token={token}",
        "--data-urlencode",
        "QueryType=modify",
        "--data-urlencode",
        "Template=list",
        "--data-urlencode",
        f"SpeakerName[]={speaker_id}",
    ]
    if page > 1:
        command.extend(["--data-urlencode", f"Page={page}"])
    return run_curl(command)


def run_curl(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as exc:
        raise ExtractionError("会議録サイトへの検索に失敗しました") from exc
    if not result.stdout.strip():
        raise ExtractionError("会議録サイトの検索結果が空でした")
    return result.stdout
