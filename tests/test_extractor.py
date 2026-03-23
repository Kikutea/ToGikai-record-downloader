from __future__ import annotations

import ssl
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from app.extractor import (
    build_extracted_document,
    build_extracted_document_for_speaker,
    fetch_url,
    parse_document,
    render_html,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class ExtractorTest(unittest.TestCase):
    def test_committee_full_mode_includes_answers(self) -> None:
        document = parse_document(load_fixture("committee_sample.html"))

        extracted = build_extracted_document(document, mode="full")

        self.assertEqual(extracted.title, "2025年（令和7年）3月18日　厚生委員会")
        self.assertEqual(extracted.category, "厚生委員会")
        self.assertEqual(len(extracted.blocks), 5)
        self.assertEqual(extracted.blocks[0].speaker, "◯さんのへ委員")
        self.assertEqual(
            extracted.blocks[1].speaker,
            "◯瀬川子供・子育て施策推進担当部長",
        )
        self.assertEqual(extracted.blocks[-1].text, "質問を終わります。")

    def test_committee_self_mode_only_keeps_own_blocks(self) -> None:
        document = parse_document(load_fixture("committee_sample.html"))

        extracted = build_extracted_document(document, mode="self")

        self.assertEqual(len(extracted.blocks), 3)
        self.assertTrue(all("さんのへ" in block.speaker for block in extracted.blocks))

    def test_plenary_title_and_body_are_formatted(self) -> None:
        document = parse_document(load_fixture("plenary_sample.html"))

        extracted = build_extracted_document(document, mode="full")
        html_output = render_html(extracted.blocks)

        self.assertEqual(extracted.title, "2025年（令和7年）3月28日　第1回定例会（第7号）")
        self.assertEqual(extracted.category, "定例会")
        self.assertEqual(len(extracted.blocks), 1)
        self.assertIn("<strong>◯十一番（さんのへあや君）</strong>", html_output)
        self.assertNotIn("（拍手）", html_output)
        self.assertNotIn("◯十一番（さんのへあや君）　私", html_output)

    def test_can_extract_other_speaker(self) -> None:
        html_text = """
        <html><body>
          <span class="command__docname">総務委員会　本文</span>
          <span class="command__date">2025-03-21</span>
          <li class="voice-block" data-voice_code="1" data-voice-title="◯上田委員">
            <p class="voice__text">◯上田委員　質問です。</p>
          </li>
          <li class="voice-block" data-voice_code="2" data-voice-title="◯担当部長">
            <p class="voice__text">◯担当部長　答弁です。</p>
          </li>
        </body></html>
        """
        document = parse_document(html_text)

        extracted = build_extracted_document_for_speaker(
            document,
            mode="full",
            target_speaker="上田令子",
        )

        self.assertEqual(extracted.target_speaker, "上田令子")
        self.assertEqual(len(extracted.blocks), 2)
        self.assertEqual(extracted.blocks[0].speaker, "◯上田委員")
        self.assertEqual(extracted.blocks[0].text, "質問です。")

    @patch("app.extractor.fetch_url_with_curl")
    @patch("app.extractor.fetch_url_with_urllib")
    def test_fetch_url_falls_back_to_curl_on_ssl_error(
        self,
        mock_urllib,
        mock_curl,
    ) -> None:
        mock_urllib.side_effect = URLError(
            ssl.SSLCertVerificationError(
                1,
                "CERTIFICATE_VERIFY_FAILED",
            )
        )
        mock_curl.return_value = "<html>ok</html>"
        result = fetch_url(
            "https://www.record.gikai.metro.tokyo.lg.jp/100000?Template=document&Id=1"
        )

        self.assertEqual(result, "<html>ok</html>")
        mock_curl.assert_called_once()


if __name__ == "__main__":
    unittest.main()
