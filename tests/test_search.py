from __future__ import annotations

import unittest
from unittest.mock import patch

from app.extractor import ExtractionError
from app.search import (
    SearchResult,
    parse_search_results,
    parse_speaker_options,
    resolve_speaker_option,
    search_documents_by_speaker,
)


SPEAKER_HTML = """
<html><body>
  <form>
    <input type="hidden" name="_token" value="token-123">
    <select name="SpeakerName[]" id="SpeakerName">
      <option value="" selected>【指定しない】</option>
      <option value="492">上田令子</option>
      <option value="5756">さんのへあや</option>
    </select>
  </form>
</body></html>
"""


RESULTS_HTML = """
<html><body>
  <ul class="result">
    <li class="result__item">
      <div class="ans-title">
        <div class="ans-title__date">2025-03-26</div>
        <div class="ans-title__name">
          <a href="https://www.record.gikai.metro.tokyo.lg.jp/100000?Template=document&amp;Id=19672#one">令和７年予算特別委員会(第６号)　本文</a>
        </div>
        <div class="ans-title__hit"><span class="ans-title__count"><strong class="color-red">2</strong> 発言ヒット</span></div>
      </div>
    </li>
    <li class="result__item">
      <div class="ans-title">
        <div class="ans-title__date">2025-03-21</div>
        <div class="ans-title__name">
          <a href="https://www.record.gikai.metro.tokyo.lg.jp/100000?Template=document&amp;Id=19732#one">令和７年総務委員会　本文</a>
        </div>
        <div class="ans-title__hit"><span class="ans-title__count"><strong class="color-red">1</strong> 発言ヒット</span></div>
      </div>
    </li>
  </ul>
</body></html>
"""


class SearchTest(unittest.TestCase):
    def test_parse_speaker_options(self) -> None:
        options = parse_speaker_options(SPEAKER_HTML)

        self.assertEqual(len(options), 2)
        self.assertEqual(options[0].speaker_id, "492")
        self.assertEqual(options[1].label, "さんのへあや")

    def test_resolve_speaker_option_prefers_exact_match(self) -> None:
        options = parse_speaker_options(SPEAKER_HTML)

        option = resolve_speaker_option("上田令子", options)

        self.assertEqual(option.speaker_id, "492")

    def test_resolve_speaker_option_rejects_unsupported_speaker(self) -> None:
        options = parse_speaker_options(SPEAKER_HTML)

        with self.assertRaisesRegex(ExtractionError, "さんのへあや / 上田令子 のみ選択できます"):
            resolve_speaker_option("小池百合子", options)

    def test_parse_search_results(self) -> None:
        results = parse_search_results(RESULTS_HTML)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].date_iso, "2025-03-26")
        self.assertEqual(results[0].hit_count, 2)
        self.assertTrue(results[0].url.endswith("Id=19672"))

    @patch("app.search.post_speaker_search")
    @patch("app.search.fetch_search_speaker_page")
    def test_search_documents_by_speaker_filters_title(
        self,
        mock_fetch_page,
        mock_post_search,
    ) -> None:
        mock_fetch_page.return_value = SPEAKER_HTML
        mock_post_search.return_value = RESULTS_HTML

        option, results = search_documents_by_speaker(
            "さんのへあや",
            max_pages=1,
            title_filter="総務",
        )

        self.assertEqual(option.speaker_id, "5756")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "令和７年総務委員会 本文")


if __name__ == "__main__":
    unittest.main()
