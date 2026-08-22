import json
import tempfile
import unittest
from pathlib import Path

from sync_firebase_rewrites import synchronize


class SyncFirebaseRewritesTest(unittest.TestCase):
    def test_generates_exact_rewrites_and_removes_generic_regexes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            public = root / "public"
            artifact = public / "computer" / "program" / "ie" / "index.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("{}", encoding="utf-8")
            firebase = root / "firebase.json"
            firebase.write_text(
                json.dumps(
                    {
                        "hosting": {
                            "rewrites": [
                                {
                                    "regex": r"^/(.+)\.json$",
                                    "destination": "/:1/index.json",
                                },
                                {"source": "/hi", "destination": "/hi/root/index.html"},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(synchronize(firebase, public), 1)
            rewrites = json.loads(firebase.read_text(encoding="utf-8"))["hosting"][
                "rewrites"
            ]
            self.assertIn(
                {
                    "source": "/computer/program/ie.json",
                    "destination": "/computer/program/ie/index.json",
                },
                rewrites,
            )
            self.assertIn({"source": "/hi", "destination": "/hi/root/index.html"}, rewrites)
            self.assertFalse(any(item.get("regex") for item in rewrites))


if __name__ == "__main__":
    unittest.main()
