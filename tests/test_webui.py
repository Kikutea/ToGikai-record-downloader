from __future__ import annotations

import unittest
from unittest.mock import patch

from app.webui import build_result_payload, render_page


class WebUITest(unittest.TestCase):
    def test_render_page_shows_error(self) -> None:
        page = render_page(
            source="abc",
            mode="self",
            speaker_name="上田令子",
            error="抽出に失敗しました",
        )

        self.assertIn("抽出に失敗しました", page)
        self.assertIn('value="abc"', page)
        self.assertIn("本人発言のみ", page)
        self.assertIn('<select id="speaker-name" name="speaker_name">', page)
        self.assertIn('<option value="上田令子" selected>上田令子</option>', page)
        self.assertNotIn("datalist", page)

    @patch("app.webui.extract_from_source")
    def test_build_result_payload_contains_all_formats(self, mock_extract) -> None:
        from app.extractor import ExtractedDocument, VoiceBlock

        mock_extract.return_value = ExtractedDocument(
            title="2025年（令和7年）3月26日　予算特別委員会（第6号）",
            date_iso="2025-03-26",
            meeting_name="予算特別委員会（第6号）",
            category="予算特別委員会",
            target_speaker="上田令子",
            blocks=[
                VoiceBlock(
                    voice_code="1",
                    speaker="◯上田委員",
                    text="質問です。\n詳細です。",
                )
            ],
        )

        payload = build_result_payload("dummy", "full", "上田令子")

        self.assertIn("<strong>◯上田委員</strong>", payload["html"])
        self.assertIn("**◯上田委員**", payload["markdown"])
        self.assertIn("◯上田委員\n質問です。", payload["text"])
        self.assertEqual(payload["category"], "予算特別委員会")
        self.assertEqual(payload["speaker_name"], "上田令子")


if __name__ == "__main__":
    unittest.main()
