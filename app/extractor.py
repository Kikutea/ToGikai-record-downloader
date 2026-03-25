from __future__ import annotations

import argparse
import dataclasses
import html
import re
import ssl
import subprocess
import unicodedata
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_SPEAKER_NAME = "さんのへあや"
SUPPORTED_SPEAKERS = ("さんのへあや", "上田令子")

KNOWN_SPEAKER_ALIASES: dict[str, tuple[str, ...]] = {
    "さんのへあや": (
        "さんのへあや",
        "さんのへ委員",
        "さんのへあや委員",
        "さんのへあや議員",
        "さんのへあや君",
    ),
    "上田令子": (
        "上田令子",
        "上田令子委員",
        "上田令子議員",
        "上田令子君",
        "上田委員",
        "上田議員",
    ),
}

PROCEDURAL_KEYWORDS = (
    "議長",
    "委員長",
    "副委員長",
    "書記",
    "議事部長",
)

OFFICIAL_KEYWORDS = (
    "知事",
    "副知事",
    "教育長",
    "部長",
    "担当部長",
    "局長",
    "理事",
    "参事",
    "室長",
    "課長",
    "主幹",
    "技監",
    "委員会統括",
)

END_PROCEDURAL_KEYWORDS = (
    "採決",
    "散会",
    "討論を終了",
    "以上をもって",
    "質疑を終了",
)


class ExtractionError(RuntimeError):
    """Raised when extraction fails with a user-facing message."""


@dataclasses.dataclass(slots=True)
class VoiceBlock:
    voice_code: str
    speaker: str
    text: str


@dataclasses.dataclass(slots=True)
class Document:
    raw_title: str
    date_iso: str
    voice_blocks: list[VoiceBlock]


@dataclasses.dataclass(slots=True)
class ExtractedDocument:
    title: str
    date_iso: str
    meeting_name: str
    category: str
    target_speaker: str
    blocks: list[VoiceBlock]


class DocumentHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doc_title = ""
        self.doc_date = ""
        self.voice_blocks: list[VoiceBlock] = []
        self._capture_target: str | None = None
        self._capture_parts: list[str] = []
        self._current_voice: dict[str, str | list[str]] | None = None
        self._in_voice_text = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        classes = set(attrs_dict.get("class", "").split())

        if tag == "span" and "command__docname" in classes:
            self._start_capture("doc_title")
            return

        if tag == "span" and "command__date" in classes:
            self._start_capture("doc_date")
            return

        if tag == "li" and "voice-block" in classes:
            self._current_voice = {
                "voice_code": attrs_dict.get("data-voice_code", ""),
                "speaker": clean_inline_text(attrs_dict.get("data-voice-title", "")),
                "text_parts": [],
            }
            return

        if (
            self._current_voice is not None
            and tag == "p"
            and "voice__text" in classes
        ):
            self._in_voice_text = True
            return

        if self._in_voice_text and tag == "br":
            text_parts = self._current_voice["text_parts"]
            assert isinstance(text_parts, list)
            text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._capture_target == "doc_title":
            self.doc_title = clean_inline_text("".join(self._capture_parts))
            self._clear_capture()
            return

        if tag == "span" and self._capture_target == "doc_date":
            self.doc_date = clean_inline_text("".join(self._capture_parts))
            self._clear_capture()
            return

        if tag == "p" and self._in_voice_text:
            self._in_voice_text = False
            return

        if tag == "li" and self._current_voice is not None:
            text_parts = self._current_voice["text_parts"]
            assert isinstance(text_parts, list)
            speaker = str(self._current_voice["speaker"])
            text = clean_block_text("".join(text_parts))
            if speaker and text:
                self.voice_blocks.append(
                    VoiceBlock(
                        voice_code=str(self._current_voice["voice_code"]),
                        speaker=speaker,
                        text=text,
                    )
                )
            self._current_voice = None

    def handle_data(self, data: str) -> None:
        if self._capture_target is not None:
            self._capture_parts.append(data)
            return

        if self._in_voice_text and self._current_voice is not None:
            text_parts = self._current_voice["text_parts"]
            assert isinstance(text_parts, list)
            text_parts.append(data)

    def _start_capture(self, target: str) -> None:
        self._capture_target = target
        self._capture_parts = []

    def _clear_capture(self) -> None:
        self._capture_target = None
        self._capture_parts = []


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("\u3000", " ").replace("\xa0", " ")
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def clean_inline_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\xa0", " ").replace("\u3000", "　")
    return re.sub(r"\s+", " ", value).strip()


def clean_block_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\xa0", " ").replace("\u00a0", " ")
    lines = [line.rstrip() for line in value.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def parse_document(html_text: str) -> Document:
    parser = DocumentHTMLParser()
    parser.feed(html_text)
    parser.close()

    if not parser.doc_title or not parser.doc_date:
        raise ExtractionError("ページ構造が想定と異なり、文書情報の取得に失敗しました")
    if not parser.voice_blocks:
        raise ExtractionError("ページ構造が想定と異なり、発言ブロックの取得に失敗しました")

    return Document(
        raw_title=parser.doc_title,
        date_iso=parser.doc_date,
        voice_blocks=parser.voice_blocks,
    )


def is_valid_source(source: str) -> bool:
    if source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        return parsed.netloc == "www.record.gikai.metro.tokyo.lg.jp"
    return Path(source).exists()


def load_source(source: str) -> str:
    if not is_valid_source(source):
        raise ExtractionError(
            "会議録本文ページの URL またはローカル HTML ファイルを指定してください"
        )

    if source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        if parsed.netloc != "www.record.gikai.metro.tokyo.lg.jp":
            raise ExtractionError("東京都議会会議録の URL を指定してください")
        if "Id=" not in source or "Template=document" not in source:
            raise ExtractionError("会議録本文ページではない可能性があります")
        return fetch_url(source)

    return Path(source).read_text(encoding="utf-8")


def fetch_url(source: str) -> str:
    try:
        return fetch_url_with_urllib(source)
    except URLError as exc:
        if not is_ssl_verification_error(exc):
            raise ExtractionError("会議録ページを取得できませんでした") from exc
    except ssl.SSLCertVerificationError:
        pass

    try:
        return fetch_url_with_curl(source)
    except Exception as exc:  # pragma: no cover - network error handling
        raise ExtractionError(
            "会議録ページを取得できませんでした。Python の証明書検証に失敗したため curl でも再試行しましたが取得できませんでした"
        ) from exc


def fetch_url_with_urllib(source: str) -> str:
    request = Request(
        source,
        headers={
            "User-Agent": "ToGikaiRecordExtractor/0.1 (+https://www.record.gikai.metro.tokyo.lg.jp)"
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def fetch_url_with_curl(source: str) -> str:
    result = subprocess.run(
        ["curl", "-L", "-s", source],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if not result.stdout.strip():
        raise ExtractionError("会議録ページを取得できませんでした")
    return result.stdout


def is_ssl_verification_error(exc: URLError) -> bool:
    reason = getattr(exc, "reason", None)
    return isinstance(reason, ssl.SSLCertVerificationError)


def normalize_speaker_name(speaker_name: str) -> str:
    speaker_name = clean_inline_text(speaker_name)
    speaker_name = re.sub(r"（[^）]*）", "", speaker_name).strip()
    speaker_name = re.sub(r"\([^)]*\)", "", speaker_name).strip()
    speaker_name = re.sub(r"(議員|委員|君)$", "", speaker_name).strip()
    return speaker_name


def validate_supported_speaker(speaker_name: str) -> str:
    normalized_name = normalize_speaker_name(speaker_name)
    if normalized_name not in SUPPORTED_SPEAKERS:
        supported = " / ".join(SUPPORTED_SPEAKERS)
        raise ExtractionError(f"発言者は {supported} のみ選択できます")
    return normalized_name


def build_target_aliases(speaker_name: str) -> tuple[str, ...]:
    normalized_name = validate_supported_speaker(speaker_name)
    aliases = {normalized_name}
    if normalized_name in KNOWN_SPEAKER_ALIASES:
        aliases.update(KNOWN_SPEAKER_ALIASES[normalized_name])

    aliases.add(f"{normalized_name}委員")
    aliases.add(f"{normalized_name}議員")
    aliases.add(f"{normalized_name}君")

    return tuple(alias for alias in aliases if alias)


def is_target_speaker(speaker: str, speaker_name: str) -> bool:
    normalized = normalize_text(speaker)
    aliases = build_target_aliases(speaker_name)
    if any(normalize_text(keyword) in normalized for keyword in aliases):
        return True
    return False


def classify_speaker(speaker: str, target_speaker: str) -> str:
    normalized = normalize_text(speaker)

    if is_target_speaker(speaker, target_speaker):
        return "self"

    if any(keyword in normalized for keyword in map(normalize_text, PROCEDURAL_KEYWORDS)):
        return "procedural"

    if any(keyword in normalized for keyword in map(normalize_text, OFFICIAL_KEYWORDS)):
        return "official"

    if "委員" in normalized or "議員" in normalized or "君)" in normalized or "君）" in normalized:
        return "other_member"

    return "other"


def is_noise_text(text: str) -> bool:
    stripped = normalize_text(text)
    if not stripped:
        return True
    if stripped.startswith("〔") and stripped.endswith("〕"):
        return True
    if set(stripped) == {"-"}:
        return True
    if set(stripped) == {"─"}:
        return True
    return False


def remove_speaker_prefix(text: str, speaker: str) -> str:
    text = text.lstrip()
    speaker_pattern = re.escape(speaker)
    text = re.sub(rf"^\s*{speaker_pattern}[ 　]*", "", text, count=1)
    return text.lstrip()


def strip_noise_from_body(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if is_noise_text(line):
            continue
        if line == "（拍手）":
            continue
        lines.append(line)
    return "\n".join(lines)


def cleaned_voice_body(block: VoiceBlock) -> str:
    body = remove_speaker_prefix(block.text, block.speaker)
    body = strip_noise_from_body(body)
    return body


def extract_blocks(
    document: Document,
    mode: str,
    target_speaker: str,
) -> list[VoiceBlock]:
    if mode == "self":
        extracted = [
            dataclasses.replace(block, text=cleaned_voice_body(block))
            for block in document.voice_blocks
            if is_target_speaker(block.speaker, target_speaker) and cleaned_voice_body(block)
        ]
    else:
        extracted = extract_full_sequence(document.voice_blocks, target_speaker)

    if not extracted:
        raise ExtractionError(f"{target_speaker}議員の発言が見つかりませんでした")

    return extracted


def extract_full_sequence(
    voice_blocks: Iterable[VoiceBlock],
    target_speaker: str,
) -> list[VoiceBlock]:
    collected: list[VoiceBlock] = []
    started = False

    for block in voice_blocks:
        speaker_type = classify_speaker(block.speaker, target_speaker)
        body = cleaned_voice_body(block)

        if not started:
            if speaker_type == "self" and body:
                started = True
                collected.append(dataclasses.replace(block, text=body))
            continue

        if speaker_type == "self":
            if body:
                collected.append(dataclasses.replace(block, text=body))
            continue

        if speaker_type == "official":
            if body:
                collected.append(dataclasses.replace(block, text=body))
            continue

        if speaker_type == "procedural":
            normalized_body = normalize_text(body)
            if any(keyword in normalized_body for keyword in map(normalize_text, END_PROCEDURAL_KEYWORDS)):
                break
            continue

        if speaker_type == "other_member":
            break

        if body:
            collected.append(dataclasses.replace(block, text=body))

    return collected


def format_meeting_name(raw_title: str) -> str:
    title = unicodedata.normalize("NFKC", raw_title).strip()
    title = re.sub(r"\s*本文$", "", title)
    title = re.sub(r"^(令和|平成|昭和)\d+年", "", title)
    title = title.replace("(", "（").replace(")", "）")
    return title.strip()


def category_from_meeting_name(meeting_name: str) -> str:
    candidates = (
        "予算特別委員会",
        "各会計決算特別委員会",
        "公営企業会計決算特別委員会",
        "議会運営委員会",
        "定例会",
        "臨時会",
    )
    for candidate in candidates:
        if candidate in meeting_name:
            return candidate
    committee_match = re.search(r"[^　 ]+委員会", meeting_name)
    if committee_match:
        return committee_match.group(0)
    return meeting_name


def japanese_era_for_date(doc_date: date) -> tuple[str, int]:
    if doc_date >= date(2019, 5, 1):
        return ("令和", doc_date.year - 2018)
    if doc_date >= date(1989, 1, 8):
        return ("平成", doc_date.year - 1988)
    if doc_date >= date(1926, 12, 25):
        return ("昭和", doc_date.year - 1925)
    raise ExtractionError("和暦へ変換できない日付です")


def build_published_title(raw_title: str, date_iso: str) -> str:
    meeting_name = format_meeting_name(raw_title)
    year, month, day = map(int, date_iso.split("-"))
    doc_date = date(year, month, day)
    era_name, era_year = japanese_era_for_date(doc_date)
    return f"{year}年（{era_name}{era_year}年）{month}月{day}日　{meeting_name}"


def build_extracted_document(document: Document, mode: str) -> ExtractedDocument:
    return build_extracted_document_for_speaker(
        document=document,
        mode=mode,
        target_speaker=DEFAULT_SPEAKER_NAME,
    )


def build_extracted_document_for_speaker(
    document: Document,
    mode: str,
    target_speaker: str,
) -> ExtractedDocument:
    meeting_name = format_meeting_name(document.raw_title)
    normalized_target = validate_supported_speaker(target_speaker)
    return ExtractedDocument(
        title=build_published_title(document.raw_title, document.date_iso),
        date_iso=document.date_iso,
        meeting_name=meeting_name,
        category=category_from_meeting_name(meeting_name),
        target_speaker=normalized_target,
        blocks=extract_blocks(document, mode, normalized_target),
    )


def extract_from_source(
    source: str,
    mode: str = "full",
    target_speaker: str = DEFAULT_SPEAKER_NAME,
) -> ExtractedDocument:
    source_html = load_source(source)
    document = parse_document(source_html)
    return build_extracted_document_for_speaker(
        document,
        mode=mode,
        target_speaker=target_speaker,
    )


def render_html(blocks: Iterable[VoiceBlock]) -> str:
    rendered = []
    for block in blocks:
        lines = [html.escape(line) for line in block.text.splitlines() if line]
        body = "<br>".join(lines)
        rendered.append(f"<p><strong>{html.escape(block.speaker)}</strong><br>{body}</p>")
    return "\n\n".join(rendered)


def render_markdown(blocks: Iterable[VoiceBlock]) -> str:
    rendered = []
    for block in blocks:
        lines = [line for line in block.text.splitlines() if line]
        body = "  \n".join(lines)
        rendered.append(f"**{block.speaker}**  \n{body}")
    return "\n\n".join(rendered)


def render_text(blocks: Iterable[VoiceBlock]) -> str:
    rendered = []
    for block in blocks:
        body = "\n".join(line for line in block.text.splitlines() if line)
        rendered.append(f"{block.speaker}\n{body}")
    return "\n\n".join(rendered)


def render_report(document: ExtractedDocument, output_format: str, body_only: bool) -> str:
    if output_format == "html":
        body = render_html(document.blocks)
    elif output_format == "markdown":
        body = render_markdown(document.blocks)
    else:
        body = render_text(document.blocks)

    if body_only:
        return body

    return (
        f"タイトル: {document.title}\n"
        f"日付: {document.date_iso}\n"
        f"会議名: {document.meeting_name}\n"
        f"カテゴリ候補: {document.category}\n\n"
        f"{body}"
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="東京都議会会議録から発言を抽出します")
    parser.add_argument("source", help="会議録本文 URL またはローカル HTML ファイル")
    parser.add_argument(
        "--speaker",
        default=DEFAULT_SPEAKER_NAME,
        choices=SUPPORTED_SPEAKERS,
        help="抽出対象の発言者名。例: さんのへあや, 上田令子",
    )
    parser.add_argument(
        "--mode",
        choices=("full", "self"),
        default="full",
        help="full=質疑全文, self=本人発言のみ",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("html", "markdown", "text"),
        default="html",
        help="出力形式",
    )
    parser.add_argument(
        "--body-only",
        action="store_true",
        help="本文のみを出力する",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        extracted = extract_from_source(
            args.source,
            mode=args.mode,
            target_speaker=args.speaker,
        )
        print(render_report(extracted, args.output_format, args.body_only))
        return 0
    except ExtractionError as exc:
        parser.exit(1, f"エラー: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
