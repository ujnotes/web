import json
import tempfile
import unittest
from pathlib import Path

import validate_sitemap


class SitemapValidationTests(unittest.TestCase):
    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_manifest_requires_every_published_translation_in_sitemap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sitemap = root / "sitemap.xml"
            translations = root / "Translations.tsv"
            self.write(sitemap, "<urlset><url><loc>https://ujnotes.com/world/example</loc></url></urlset>")
            self.write(translations, "TranslationGroup\ten\thi\nworld/example\tpublished\tpublished\n")
            urls = validate_sitemap.sitemap_urls(sitemap)
            missing = validate_sitemap.expected_translation_urls(translations, "https://ujnotes.com") - set(urls)
            self.assertEqual({"https://ujnotes.com/hi/world/example"}, missing)

    def test_local_validation_flags_metadata_preamble(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            page = root / "public/hi/world/example"
            self.write(page / "index.html", "<p>Language: hi Label: X Title: X Description: X</p>")
            self.write(page / "index.json", json.dumps({"content": "Clean article"}))
            errors = validate_sitemap.validate_local(["https://ujnotes.com/hi/world/example"], "https://ujnotes.com", root / "public")
            self.assertIn("Translation metadata leaked into HTML: https://ujnotes.com/hi/world/example", errors)

    def test_duplicate_urls_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sitemap = Path(temp_dir) / "sitemap.xml"
            self.write(sitemap, "<urlset><url><loc>https://ujnotes.com/a</loc></url><url><loc>https://ujnotes.com/a</loc></url></urlset>")
            with self.assertRaisesRegex(RuntimeError, "Duplicate sitemap URLs"):
                validate_sitemap.sitemap_urls(sitemap)


if __name__ == "__main__":
    unittest.main()
