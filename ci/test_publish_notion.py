import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import publish_notion


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


class PublicationMergeTests(unittest.TestCase):
    def make_fixture(self, root):
        root = Path(root)
        bundle = root / "bundle"
        source = root / "source"
        public_repo = root / "public-repo"
        metadata_path = root / "article.json"
        slug = "world/example"

        write(
            bundle / "HTML/Component/world/example/index.php",
            "<div id='message'>Example</div>",
        )
        write(
            bundle / "Config/ID.tsv",
            "Status\tId\tLabel\tTitle\tJS\tDescription\tType\n"
            "publish\tworld/example\tExample\tExample\t0\tDescription\tarticle\n",
        )
        write(
            source / "Config/ID.tsv",
            "Status\tId\tLabel\tTitle\tJS\tDescription\tType\n"
            "published\tabout\tAbout\tAbout\t0\tExisting\tpage\n",
        )
        write(
            source / "Config/Url.tsv",
            "Path\tName\tExtension\n"
            "\tscript\tjs\n"
            "\tstyle\tcss\n"
            "about/\tindex\tjpg\n"
            "world/other/\tindex\tjpg\n",
        )
        write(
            source / "Root/Site/SiteMap.xml",
            "<?xml version='1.0'?><urlset><url><loc>https://ujnotes.com/about</loc>"
            "</url></urlset>",
        )
        write(source / "Root/Resource/world/example/index.jpg", "cover")

        metadata = {
            "page_id": "page-1",
            "slug": slug,
            "title": "Example",
            "description": "Description",
            "language": "en",
            "component": "HTML/Component/world/example/index.php",
            "queued_slugs": [slug],
        }
        write(metadata_path, json.dumps(metadata))

        write(
            public_repo / "firebase.json",
            json.dumps(
                {
                    "hosting": {
                        "public": "./public",
                        "redirects": [
                            {"source": "/about-me", "destination": "/about", "type": 301}
                        ],
                        "rewrites": [
                            {"source": "/about.json", "destination": "/about/index.json"}
                        ],
                    }
                }
            ),
        )
        write(
            public_repo / "public/sitemap.xml",
            "<?xml version='1.0'?><urlset><url><loc>https://ujnotes.com/about</loc>"
            "</url></urlset>",
        )
        return bundle, source, public_repo, metadata_path

    def test_source_merge_preserves_existing_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle, source, _, metadata_path = self.make_fixture(temp_dir)
            publish_notion.prepare_source(
                SimpleNamespace(
                    bundle=str(bundle),
                    metadata=str(metadata_path),
                    source=str(source),
                    base_url="https://ujnotes.com",
                )
            )

            id_text = (source / "Config/ID.tsv").read_text(encoding="utf-8")
            self.assertIn("published\tabout", id_text)
            self.assertIn("publish\tworld/example", id_text)
            url_text = (source / "Config/Url.tsv").read_text(encoding="utf-8")
            self.assertIn("about/\tindex\tjpg", url_text)
            self.assertIn("world/example/\tindex\tjpg", url_text)
            component = source / "Root/HTML/Component/world/example/index.php"
            self.assertIn("Component_cover.php", component.read_text(encoding="utf-8"))
            sitemap = (source / "Root/Site/SiteMap.xml").read_text(encoding="utf-8")
            self.assertIn("https://ujnotes.com/about", sitemap)
            self.assertIn("https://ujnotes.com/world/example", sitemap)

    def test_stage_keeps_script_url_and_selected_article_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle, source, _, metadata_path = self.make_fixture(temp_dir)
            publish_notion.prepare_source(
                SimpleNamespace(
                    bundle=str(bundle),
                    metadata=str(metadata_path),
                    source=str(source),
                    base_url="https://ujnotes.com",
                )
            )
            stage = Path(temp_dir) / "stage"
            publish_notion.create_stage(
                SimpleNamespace(
                    metadata=str(metadata_path),
                    source=str(source),
                    stage=str(stage),
                )
            )

            url_text = (stage / "Config/Url.tsv").read_text(encoding="utf-8")
            self.assertIn("\tscript\tjs", url_text)
            self.assertNotIn("\tstyle\tcss", url_text)
            self.assertIn("world/example/\tindex\tjpg", url_text)
            self.assertNotIn("about/\tindex\tjpg", url_text)
            self.assertNotIn("world/other/\tindex\tjpg", url_text)
            id_text = (stage / "Config/ID.tsv").read_text(encoding="utf-8")
            self.assertIn("publish\tworld/example", id_text)
            self.assertNotIn("published\tabout", id_text)

    def test_public_merge_preserves_firebase_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle, source, public_repo, metadata_path = self.make_fixture(temp_dir)
            publish_notion.prepare_source(
                SimpleNamespace(
                    bundle=str(bundle),
                    metadata=str(metadata_path),
                    source=str(source),
                    base_url="https://ujnotes.com",
                )
            )
            stage = Path(temp_dir) / "stage"
            write(stage / "public/world/example/index.html", "<html>Example</html>")
            write(
                stage / "public/world/example/index.json",
                json.dumps({"desc": "Description", "content": "Example"}),
            )
            write(stage / "public/world/example/index.jpg", "cover")

            publish_notion.publish_artifacts(
                SimpleNamespace(
                    metadata=str(metadata_path),
                    stage=str(stage),
                    public_repo=str(public_repo),
                    base_url="https://ujnotes.com",
                )
            )

            firebase = json.loads(
                (public_repo / "firebase.json").read_text(encoding="utf-8")
            )["hosting"]
            self.assertIn(
                {"source": "/about-me", "destination": "/about", "type": 301},
                firebase["redirects"],
            )
            self.assertIn(
                {
                    "source": "/world/example.json",
                    "destination": "/world/example/index.json",
                },
                firebase["rewrites"],
            )
            self.assertTrue(
                (public_repo / "public/world/example/index.json").is_file()
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(64, len(metadata["json_sha256"]))

    def test_conflicting_shortcut_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            firebase_path = Path(temp_dir) / "firebase.json"
            write(
                firebase_path,
                json.dumps(
                    {
                        "hosting": {
                            "redirects": [
                                {
                                    "source": "/example",
                                    "destination": "/another/example",
                                    "type": 301,
                                }
                            ],
                            "rewrites": [],
                        }
                    }
                ),
            )
            with self.assertRaisesRegex(RuntimeError, "already points"):
                publish_notion.merge_firebase(
                    firebase_path, "world/example", has_cover=False
                )


if __name__ == "__main__":
    unittest.main()
