"""Test delle parti pure del progetto (nessuna rete necessaria).

Esecuzione:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unittest import mock

from src.config import Config, ConfigError, load_config
from src.main import _md_escape, is_recent
from src.state import StateStore
from src.summarizer import _extract_summary, summarize_notice

# Variabili d'ambiente lette da load_config: vanno rimosse durante i test
# per evitare che valori esportati nella shell (o un .env reale) inquinino
# i fixture temporanei (os.environ ha priorità sul file .env).
CONFIG_KEYS = (
    "CV_UID", "CV_PASSWORD", "CV_CID", "CV_PIN", "MARK_AS_READ",
    "TG_BOT_TOKEN", "TG_CHAT_ID", "LLM_API_URL", "LLM_API_KEY",
    "LLM_MODEL", "BACKFILL_DAYS", "REQUEST_DELAY",
)


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {k: os.environ.pop(k) for k in CONFIG_KEYS if k in os.environ}

    def tearDown(self) -> None:
        os.environ.update(self._saved_env)

    def _write_env(self, content: str) -> Path:
        tmp = Path(tempfile.mkdtemp()) / ".env"
        tmp.write_text(content, encoding="utf-8")
        return tmp

    def test_missing_required_fields_raise(self) -> None:
        env = self._write_env("CV_UID=user\n")
        with self.assertRaises(ConfigError):
            load_config(env)

    def test_mark_as_read_defaults_false(self) -> None:
        env = self._write_env(
            "CV_UID=u\nCV_PASSWORD=p\nTG_BOT_TOKEN=t\nTG_CHAT_ID=1\n"
        )
        cfg = load_config(env)
        self.assertFalse(cfg.mark_as_read)

    def test_mark_as_read_explicit_true(self) -> None:
        env = self._write_env(
            "CV_UID=u\nCV_PASSWORD=p\nTG_BOT_TOKEN=t\nTG_CHAT_ID=1\nMARK_AS_READ=true\n"
        )
        cfg = load_config(env)
        self.assertTrue(cfg.mark_as_read)

    def test_llm_url_completed_with_chat_completions(self) -> None:
        env = self._write_env(
            "CV_UID=u\nCV_PASSWORD=p\nTG_BOT_TOKEN=t\nTG_CHAT_ID=1\n"
            "LLM_API_URL=https://openrouter.ai/api/v1\n"
        )
        cfg = load_config(env)
        self.assertEqual(cfg.llm_api_url, "https://openrouter.ai/api/v1/chat/completions")

    def test_llm_url_kept_when_already_complete(self) -> None:
        env = self._write_env(
            "CV_UID=u\nCV_PASSWORD=p\nTG_BOT_TOKEN=t\nTG_CHAT_ID=1\n"
            "LLM_API_URL=https://api.openai.com/v1/chat/completions\n"
        )
        cfg = load_config(env)
        self.assertEqual(cfg.llm_api_url, "https://api.openai.com/v1/chat/completions")

    def test_quoted_values_and_comments(self) -> None:
        env = self._write_env(
            '# commento\nCV_UID="user x"\nCV_PASSWORD=p\n'
            "TG_BOT_TOKEN=t\nTG_CHAT_ID=1\nBACKFILL_DAYS=30\n"
        )
        cfg = load_config(env)
        self.assertEqual(cfg.cv_uid, "user x")
        self.assertEqual(cfg.backfill_days, 30)


class StateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Path(tempfile.mkdtemp()) / "test.db"
        self.state = StateStore(self.db)

    def tearDown(self) -> None:
        self.state.close()

    def test_mark_and_check(self) -> None:
        self.assertFalse(self.state.is_processed("111"))
        self.state.mark_processed("111", "CF", title="Circolare test")
        self.assertTrue(self.state.is_processed("111"))
        self.assertEqual(self.state.count(), 1)

    def test_upsert_keeps_single_row(self) -> None:
        self.state.mark_processed("222", "CF", status="ok")
        self.state.mark_processed("222", "CF", status="failed")
        self.assertEqual(self.state.count(), 1)

    def test_persistence_across_instances(self) -> None:
        self.state.mark_processed("333", "CF")
        self.state.close()
        reopened = StateStore(self.db)
        try:
            self.assertTrue(reopened.is_processed("333"))
        finally:
            reopened.close()


class HelpersTest(unittest.TestCase):
    def test_md_escape(self) -> None:
        self.assertEqual(_md_escape("a_b*c`d[e"), r"a\_b\*c\`d\[e")

    def test_is_recent_true(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.assertTrue(is_recent({"pubDT": now}, 7))

    def test_is_recent_false_for_old(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.assertFalse(is_recent({"pubDT": old}, 7))

    def test_is_recent_tolerates_bad_date(self) -> None:
        self.assertTrue(is_recent({"pubDT": "non-una-data"}, 7))
        self.assertTrue(is_recent({}, 7))


class SummarizerTest(unittest.TestCase):
    def _cfg_no_llm(self) -> Config:
        # Config senza LLM: summarize_notice usa la sintesi grezza (nessuna rete)
        return Config(
            cv_uid="u", cv_password="p", cv_cid="", cv_pin="", mark_as_read=False,
            tg_bot_token="t", tg_chat_id="1",
            llm_api_url="", llm_api_key="", llm_model="",
            backfill_days=7, request_delay=0.0,
        )

    def test_document_includes_date_and_category(self) -> None:
        out = summarize_notice(
            "Titolo X", "", [], self._cfg_no_llm(),
            notice_date="2026-02-10", category="Circolari",
        )
        self.assertIn("Titolo X", out)
        self.assertIn("2026-02-10", out)
        self.assertIn("Circolari", out)

    def test_omits_empty_date_and_category(self) -> None:
        out = summarize_notice("Titolo Y", "", [], self._cfg_no_llm())
        self.assertNotIn("Data della comunicazione", out)
        self.assertNotIn("Categoria:", out)

    def _cfg_with_llm(self) -> Config:
        return Config(
            cv_uid="u", cv_password="p", cv_cid="", cv_pin="", mark_as_read=False,
            tg_bot_token="t", tg_chat_id="1",
            llm_api_url="https://example.test/v1/chat/completions",
            llm_api_key="k", llm_model="m",
            backfill_days=7, request_delay=0.0,
        )

    def test_extract_summary_normal(self) -> None:
        data = {"choices": [{"message": {"content": "  Ciao  "}, "finish_reason": "stop"}]}
        self.assertEqual(_extract_summary(data), "Ciao")

    def test_extract_summary_none_content_with_reasoning(self) -> None:
        # Scenario del crash reale: modelli reasoning con max_tokens esaurito
        data = {"choices": [{"message": {"content": None, "reasoning": "pensiero…"},
                             "finish_reason": "length"}]}
        with self.assertRaises(ValueError):
            _extract_summary(data)

    def test_extract_summary_empty_content(self) -> None:
        data = {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
        with self.assertRaises(ValueError):
            _extract_summary(data)

    def test_extract_summary_missing_choices(self) -> None:
        with self.assertRaises(ValueError):
            _extract_summary({})

    def test_llm_null_content_falls_back_to_excerpt(self) -> None:
        resp = mock.Mock()
        resp.text = ""
        resp.json.return_value = {"choices": [{"message": {"content": None, "reasoning": "x"},
                                               "finish_reason": "length"}]}
        resp.raise_for_status.return_value = None
        with mock.patch("src.summarizer.requests.post", return_value=resp):
            out = summarize_notice("Titolo Z", "corpo", [], self._cfg_with_llm(),
                                   notice_date="2026-02-10")
        self.assertIn("Sintesi automatica non disponibile", out)
        self.assertIn("Titolo Z", out)
        self.assertIn("2026-02-10", out)


if __name__ == "__main__":
    unittest.main()