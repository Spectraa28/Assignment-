import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import classify


ANSWER = {
    "type": "choice", "choice": "acceptable",
    "probabilities": {"acceptable": 0.8, "toxic": 0.1, "spam": 0.1}, "confidence": 0.7,
}
DATASET = {
    "course": "Test course",
    "comments": [
        {"id": i, "author": "Test student", "thread": "Test thread", "posted_at": "2026-10-27",
         "comment": '<script>alert("test")</script> & sample text'}
        for i in (1, 2)
    ],
}


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.patch = patch.object(classify, "BASE", self.base)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.base / "comments.json").write_text(json.dumps(DATASET))
        (self.base / "cloud-flare.local.sh").write_text(
            'export CLOUDFLARE_ACCOUNT_ID="' + 'a' * 32 + '"\n'
            'export CLOUDFLARE_API_TOKEN="synthetic-test-token"\n'
        )

    def run_main(self, *args):
        with patch("sys.argv", ["classify.py", *args]), patch("sys.stdout", new_callable=io.StringIO):
            classify.main()

    def test_complete_run_and_cached_report_make_no_repeat_calls(self):
        body = {"success": True, "result": {"answers": {"moderation": ANSWER},
                                              "usage": {"input_tokens": 100, "output_tokens": 0}}}
        with patch("urllib.request.urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps(body).encode())) as api:
            self.run_main()
            self.assertEqual(api.call_count, 2)
            request = api.call_args.args[0]
            self.assertTrue(request.full_url.endswith("/@cf/cloudflare/clef-flash"))
            self.assertEqual(json.loads(request.data)["state"]["comment"], DATASET["comments"][1]["comment"])
            self.run_main()
            self.run_main("--report-only")
            self.assertEqual(api.call_count, 2)
        cache = json.loads((self.base / "results.json").read_text())
        self.assertEqual([r["id"] for r in cache["results"]], [1, 2])
        page = (self.base / "report.html").read_text()
        self.assertIn("2 of 2 classified", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        for file in ("report.html", "results.json"):
            self.assertNotIn("synthetic-test-token", (self.base / file).read_text())
        self.assertFalse((self.base / "MISTAKES.md").exists())

    def test_failed_run_saves_progress_and_resumes_remaining_comment(self):
        record = {"id": 1, "answer": ANSWER, "usage": {}}
        with patch.object(classify, "classify", side_effect=[record, ValueError("API failed")]):
            with self.assertRaisesRegex(ValueError, "API failed"):
                self.run_main()
        self.assertIn("1 of 2 classified", (self.base / "report.html").read_text())
        self.assertIn("Not classified yet", (self.base / "report.html").read_text())
        with patch.object(classify, "classify", return_value={**record, "id": 2}) as api:
            self.run_main()
            self.assertEqual(api.call_count, 1)
            self.assertEqual(api.call_args.args[0]["id"], 2)

    def test_v2_uses_larger_model_and_separate_files(self):
        (self.base / "comments-v2.json").write_text(json.dumps(DATASET))
        body = {"success": True, "result": {"answers": {"moderation": ANSWER}}}
        with patch("urllib.request.urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps(body).encode())) as api:
            self.run_main("--v2")
            self.assertTrue(api.call_args.args[0].full_url.endswith("/@cf/cloudflare/clef"))
            self.run_main("--v2", "--report-only")
            self.assertEqual(api.call_count, 2)
        cache = json.loads((self.base / "results-v2.json").read_text())
        self.assertEqual(cache["model"], "clef")
        page = (self.base / "results-v2.html").read_text()
        self.assertIn("MISTAKES-v2.md", page)
        self.assertIn("Model: clef</p>", page)
        self.assertFalse((self.base / "results.json").exists())
        self.assertFalse((self.base / "report.html").exists())
        self.assertFalse((self.base / "MISTAKES-v2.md").exists())

    def test_invalid_api_answers_are_rejected(self):
        for change in ({"choice": "other"}, {"confidence": float("nan")},
                       {"probabilities": {"acceptable": 1}}, {"confidence": 2},
                       {"probabilities": {"acceptable": 0.9, "toxic": 0.9, "spam": 0.9}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                classify.validate_answer({**copy.deepcopy(ANSWER), **change})

    def test_http_errors_do_not_expose_credentials_or_retry(self):
        error = urllib.error.HTTPError("https://api.cloudflare.com/", 429, "synthetic-test-token", {}, None)
        with patch("urllib.request.urlopen", side_effect=error) as api:
            with self.assertRaisesRegex(ValueError, "HTTP 429") as raised:
                classify.classify(DATASET["comments"][0], "Test course", "a" * 32, "synthetic-test-token")
            self.assertNotIn("synthetic-test-token", str(raised.exception))
            self.assertEqual(api.call_count, 1)

    def test_changed_inputs_do_not_overwrite_saved_results(self):
        with patch.object(classify, "classify", side_effect=lambda row, *args: {"id": row["id"], "answer": ANSWER}):
            self.run_main()
        original = (self.base / "results.json").read_bytes()
        changed = copy.deepcopy(DATASET)
        changed["comments"][0]["comment"] = "Changed text"
        (self.base / "comments.json").write_text(json.dumps(changed))
        with patch.object(classify, "classify") as api:
            with self.assertRaisesRegex(ValueError, "different input"):
                self.run_main()
            api.assert_not_called()
        self.assertEqual(original, (self.base / "results.json").read_bytes())

    def test_placeholders_and_duplicate_ids_fail_before_api_calls(self):
        (self.base / "cloud-flare.local.sh").write_text(
            'export CLOUDFLARE_ACCOUNT_ID="0123456789abcdef0123456789abcdef"\n'
            'export CLOUDFLARE_API_TOKEN="your-cloudflare-api-token-goes-here"\n'
        )
        with patch.object(classify, "classify") as api:
            with self.assertRaisesRegex(ValueError, "placeholders"):
                self.run_main()
            duplicate = copy.deepcopy(DATASET)
            duplicate["comments"][1]["id"] = 1
            (self.base / "comments.json").write_text(json.dumps(duplicate))
            with self.assertRaisesRegex(ValueError, "unique integer id"):
                self.run_main()
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
