import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).parents[1] / "skills/pdf-digest/scripts/pdf_digest.py"
SPEC = importlib.util.spec_from_file_location("pdf_digest_under_test", SCRIPT)
assert SPEC and SPEC.loader
pdf_digest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pdf_digest
SPEC.loader.exec_module(pdf_digest)


class PdfDigestDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tempdir.name)
        self.original_state_dir = pdf_digest.STATE_DIR
        pdf_digest.STATE_DIR = self.state_dir
        self.doc = {
            "id": "test-document",
            "short_id": "testdoc",
            "title": "test.pdf",
            "status": "active",
            "paths": {
                "pdf": str(self.state_dir / "inbox/test.pdf"),
                "history": str(self.state_dir / "history/test.jsonl"),
            },
            "next_chunk_index": 0,
            "total_chunks": 1,
            "last_sent_at": None,
            "last_error": None,
            "pending_delivery": None,
        }
        self.state = {"version": 1, "documents": [self.doc]}
        self.chunks = [{"index": 0, "text": "sample"}]
        self.original_summarize = pdf_digest.summarize_chunk
        self.original_send = pdf_digest.send_slack_message
        pdf_digest.summarize_chunk = lambda *_args, **_kwargs: "summary"

    def tearDown(self):
        pdf_digest.STATE_DIR = self.original_state_dir
        pdf_digest.summarize_chunk = self.original_summarize
        pdf_digest.send_slack_message = self.original_send
        self.tempdir.cleanup()

    def test_successful_send_advances_progress_and_clears_pending_marker(self):
        pdf_digest.send_slack_message = lambda *_args, **_kwargs: None

        pdf_digest.send_next_chunk(self.state, self.doc, self.chunks, "user:test", False)

        persisted = json.loads((self.state_dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(self.doc["next_chunk_index"], 1)
        self.assertEqual(self.doc["status"], "done")
        self.assertIsNone(self.doc["pending_delivery"])
        self.assertEqual(persisted["documents"][0]["next_chunk_index"], 1)

    def test_failed_send_leaves_marker_and_blocks_automatic_resend(self):
        attempts = 0

        def fail_send(*_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            raise pdf_digest.PdfDigestError("transport failed")

        pdf_digest.send_slack_message = fail_send

        with self.assertRaisesRegex(pdf_digest.PdfDigestError, "transport failed"):
            pdf_digest.send_next_chunk(self.state, self.doc, self.chunks, "user:test", False)
        with self.assertRaisesRegex(pdf_digest.PdfDigestError, "Slack送信結果が未確定"):
            pdf_digest.send_next_chunk(self.state, self.doc, self.chunks, "user:test", False)

        persisted = json.loads((self.state_dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(attempts, 1)
        self.assertEqual(self.doc["next_chunk_index"], 0)
        self.assertEqual(persisted["documents"][0]["pending_delivery"]["chunk_index"], 0)

    def test_pending_delivery_can_be_reopened_for_an_explicit_retry(self):
        self.doc["pending_delivery"] = {"chunk_index": 0, "started_at": "2026-08-01T08:00:00+09:00"}
        pdf_digest.save_state(self.state)

        pdf_digest.resolve_pending_delivery(SimpleNamespace(short_id="testdoc", sent=False, retry=True))

        persisted = json.loads((self.state_dir / "state.json").read_text(encoding="utf-8"))
        self.assertIsNotNone(self.doc["pending_delivery"])
        self.assertIsNone(persisted["documents"][0]["pending_delivery"])
        self.assertEqual(persisted["documents"][0]["next_chunk_index"], 0)

    def test_pending_delivery_can_be_confirmed_as_sent(self):
        self.doc["pending_delivery"] = {"chunk_index": 0, "started_at": "2026-08-01T08:00:00+09:00"}
        pdf_digest.save_state(self.state)

        pdf_digest.resolve_pending_delivery(SimpleNamespace(short_id="testdoc", sent=True, retry=False))

        persisted = json.loads((self.state_dir / "state.json").read_text(encoding="utf-8"))
        self.assertIsNone(persisted["documents"][0]["pending_delivery"])
        self.assertEqual(persisted["documents"][0]["next_chunk_index"], 1)
        self.assertEqual(persisted["documents"][0]["status"], "done")

    def test_missing_openclaw_binary_has_a_clear_error(self):
        original = pdf_digest.OPENCLAW_BIN
        pdf_digest.OPENCLAW_BIN = None
        try:
            with self.assertRaisesRegex(pdf_digest.PdfDigestError, "openclaw コマンドがPATHで見つかりません"):
                pdf_digest.require_openclaw_bin()
        finally:
            pdf_digest.OPENCLAW_BIN = original

    def test_obsidian_export_is_enabled_by_default_and_can_be_disabled(self):
        parser = pdf_digest.build_parser()

        for argv in (
            ["register"],
            ["register-downloaded", "/tmp/example.pdf"],
            ["daily"],
        ):
            self.assertTrue(parser.parse_args(argv).export_obsidian)

        self.assertFalse(parser.parse_args(["daily", "--no-export-obsidian"]).export_obsidian)


if __name__ == "__main__":
    unittest.main()
