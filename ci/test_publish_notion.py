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
        write(source / "Root/Resource/World/Philosophy/Index.jpg", "parent-image")

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
            self.assertIn("published\tworld/example", id_text)
            self.assertNotIn("\npublish\tworld/example", id_text)
            url_text = (source / "Config/Url.tsv").read_text(encoding="utf-8")
            self.assertIn("about/\tindex\tjpg", url_text)
            self.assertIn("world/example/\tindex\tjpg", url_text)
            component = source / "Root/HTML/Component/world/example/index.php"
            self.assertIn("Component_cover.php", component.read_text(encoding="utf-8"))
            sitemap = (source / "Root/Site/SiteMap.xml").read_text(encoding="utf-8")
            self.assertIn("https://ujnotes.com/about", sitemap)
            self.assertIn("https://ujnotes.com/world/example", sitemap)

    def test_stage_renders_only_affected_pages_and_selected_urls(self):
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
            self.assertIn("published\tworld/example", id_text)
            self.assertNotIn("\npublish\tworld/example", id_text)
            self.assertNotIn("published\tabout", id_text)
            self.assertEqual(
                "parent-image",
                (
                    stage / "Root/Resource/World/Philosophy/Index.jpg"
                ).read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "parent-image",
                (
                    source / "Root/Resource/World/Philosophy/Index.jpg"
                ).read_text(encoding="utf-8"),
            )

    def test_legacy_title_cased_component_is_available_at_requested_stage_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stage = Path(temp_dir) / "stage"
            legacy = stage / "Root/HTML/Component/World/Philosophy/index.php"
            root_component = stage / "Root/HTML/Component/Root.php"
            write(legacy, "<?php echo 'Philosophy'; ?>")
            write(root_component, "<?php echo 'Root'; ?>")

            materialized = publish_notion.materialize_component_alias(
                stage, "world/philosophy"
            )
            materialized_root = publish_notion.materialize_component_alias(
                stage, "root"
            )

            requested = (
                stage / "Root/HTML/Component/world/philosophy/index.php"
            )
            requested_root = stage / "Root/HTML/Component/root.php"
            self.assertEqual(requested, materialized)
            self.assertEqual(requested_root, materialized_root)
            self.assertTrue(requested.is_file())
            self.assertTrue(requested_root.is_file())
            self.assertEqual(
                "<?php echo 'Philosophy'; ?>",
                requested.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "<?php echo 'Root'; ?>",
                requested_root.read_text(encoding="utf-8"),
            )

    def test_title_cased_cover_is_resolved_without_source_alias(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            title_cased = source / "Root/Resource/World/Philosophy/Hindu/Index.jpg"
            write(title_cased, "hindu-cover")

            resolved = publish_notion.resolve_case_insensitive(
                source, "Root/Resource/world/philosophy/hindu/index.jpg"
            )

            self.assertEqual(
                ("Root", "Resource", "World", "Philosophy", "Hindu", "Index.jpg"),
                resolved.relative_to(source).parts,
            )
            self.assertEqual(1, len(list((source / "Root/Resource").rglob("*.*"))))

    def test_affected_navigation_includes_ancestors_and_adjacent_siblings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            id_path = Path(temp_dir) / "ID.tsv"
            write(
                id_path,
                "Status\tId\n"
                "published\troot\n"
                "published\tworld\n"
                "published\tworld/philosophy\n"
                "published\tworld/philosophy/previous\n"
                "published\tworld/philosophy/hindu\n"
                "published\tworld/philosophy/next\n"
                "published\tcomputer\n",
            )

            affected = publish_notion.affected_navigation_slugs(
                id_path, "world/philosophy/hindu"
            )

            self.assertEqual(
                [
                    "root",
                    "world",
                    "world/philosophy",
                    "world/philosophy/previous",
                    "world/philosophy/hindu",
                    "world/philosophy/next",
                ],
                affected,
            )

    def test_php_diagnostic_artifact_is_rejected(self):
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
            write(
                stage / "public/world/example/index.html",
                "<b>Warning</b>: file_get_contents failed in /app/page.php on line 3",
            )
            write(
                stage / "public/world/example/index.json",
                json.dumps({"desc": "Description", "content": "Example"}),
            )

            with self.assertRaisesRegex(RuntimeError, "PHP diagnostic"):
                publish_notion.publish_artifacts(
                    SimpleNamespace(
                        metadata=str(metadata_path),
                        stage=str(stage),
                        public_repo=str(public_repo),
                        base_url="https://ujnotes.com",
                    )
                )

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

    def test_publication_copies_affected_ancestor_pages(self):
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
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["affected_slugs"] = ["root", "world", "world/example"]
            write(metadata_path, json.dumps(metadata))

            stage = Path(temp_dir) / "stage"
            write(stage / "public/index.html", "<html>Root</html>")
            write(stage / "public/root.json", json.dumps({"content": "Root"}))
            write(stage / "public/world/index.html", "<html>World</html>")
            write(stage / "public/world/index.json", json.dumps({"content": "World"}))
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

            self.assertTrue((public_repo / "public/index.html").is_file())
            self.assertTrue((public_repo / "public/root.json").is_file())
            self.assertTrue((public_repo / "public/world/index.html").is_file())
            self.assertTrue((public_repo / "public/world/index.json").is_file())
            published = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertIn("public/world/index.html", published["public_paths"])
            self.assertIn("public/world/index.json", published["public_paths"])

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
