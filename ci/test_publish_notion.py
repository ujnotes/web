import json
import os
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

    def test_merge_url_row_initializes_empty_language_map(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            url_path = Path(temp_dir) / "Url_hi.tsv"
            write(url_path, "")

            publish_notion.merge_url_row(url_path, "world/example", has_cover=True)

            self.assertEqual(
                "Path\tName\tExtension\nworld/example/\tindex\tjpg\n",
                url_path.read_text(encoding="utf-8"),
            )
    def test_rewrite_backed_asset_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            public_repo = Path(temp_dir)
            write(public_repo / "public/world/index.jpg", "cover")
            write(
                public_repo / "firebase.json",
                json.dumps(
                    {
                        "hosting": {
                            "rewrites": [
                                {
                                    "source": "/world.jpg",
                                    "destination": "/world/index.jpg",
                                }
                            ]
                        }
                    }
                ),
            )

            self.assertTrue(
                publish_notion.published_asset_exists(
                    public_repo, public_repo / "public", "world.jpg"
                )
            )
            self.assertFalse(
                publish_notion.published_asset_exists(
                    public_repo, public_repo / "public", "missing.js"
                )
            )


    def test_translation_manifest_clears_removed_language_without_whitespace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Translations.tsv"
            write(
                path,
                "TranslationGroup\ten\thi\n"
                "world/other\tpublish\t\n"
                "world/example\tpublished\tpublished\n",
            )

            publish_notion.merge_translation_manifest(
                path, "world/example", ["en"]
            )

            self.assertEqual(
                "TranslationGroup\ten\thi\n"
                "world/other\tpublish\n"
                "world/example\tpublished\n",
                path.read_text(encoding="utf-8"),
            )


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

    def test_source_merge_reuses_legacy_component_casing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle, source, _, metadata_path = self.make_fixture(temp_dir)
            legacy_component = (
                source / "Root/HTML/Component/World/Example/index.php"
            )
            write(legacy_component, "<div>Legacy</div>")

            publish_notion.prepare_source(
                SimpleNamespace(
                    bundle=str(bundle),
                    metadata=str(metadata_path),
                    source=str(source),
                    base_url="https://ujnotes.com",
                )
            )

            self.assertIn(
                "<div id='message'>Example</div>",
                legacy_component.read_text(encoding="utf-8"),
            )
            prepared = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(
                "Root/HTML/Component/World/Example/index.php",
                prepared["source_component"],
            )
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
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["affected_slugs"] = ["root", "world", "world/example"]
            write(metadata_path, json.dumps(metadata))
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
            self.assertNotIn("world/example/\tindex\tjpg", url_text)
            self.assertNotIn("about/\tindex\tjpg", url_text)
            self.assertNotIn("world/other/\tindex\tjpg", url_text)
            id_text = (stage / "Config/ID.tsv").read_text(encoding="utf-8")
            self.assertIn("published\tworld/example", id_text)
            self.assertNotIn("\npublish\tworld/example", id_text)
            self.assertIn("published\tabout", id_text)
            self.assertEqual(
                ["root", "world", "world/example"],
                (stage / "Config/Render.lsv")
                .read_text(encoding="utf-8")
                .splitlines(),
            )
            self.assertEqual(
                "parent-image",
                (
                    stage / "Root/Resource/world/philosophy/index.jpg"
                ).read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "parent-image",
                (
                    source / "Root/Resource/World/Philosophy/Index.jpg"
                ).read_text(encoding="utf-8"),
            )

    def test_stage_normalization_merges_legacy_and_lowercase_component_trees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stage = Path(temp_dir) / "stage"
            legacy = stage / "Root/HTML/Component/World/index.php"
            generated = (
                stage
                / "Root/HTML/Component/world/philosophy/hindu/index.php"
            )
            root_component = stage / "Root/HTML/Component/Root.php"
            resource = (
                stage / "Root/Resource/World/Philosophy/Hindu/Index.jpg"
            )
            write(legacy, "<?php echo 'World'; ?>")
            write(generated, "<?php echo 'Hindu'; ?>")
            write(root_component, "<?php echo 'Root'; ?>")
            write(resource, "cover")

            publish_notion.normalize_tree_lowercase(
                stage / "Root/HTML/Component"
            )
            publish_notion.normalize_tree_lowercase(stage / "Root/Resource")

            self.assertTrue(
                (stage / "Root/HTML/Component/world/index.php").is_file()
            )
            self.assertTrue(
                (
                    stage
                    / "Root/HTML/Component/world/philosophy/hindu/index.php"
                ).is_file()
            )
            self.assertTrue(
                (stage / "Root/HTML/Component/root.php").is_file()
            )
            self.assertTrue(
                (
                    stage
                    / "Root/Resource/world/philosophy/hindu/index.jpg"
                ).is_file()
            )
            if os.name != "nt":
                component_names = {
                    child.name
                    for child in (stage / "Root/HTML/Component").iterdir()
                }
                self.assertIn("world", component_names)
                self.assertNotIn("World", component_names)
                self.assertIn("root.php", component_names)
                self.assertNotIn("Root.php", component_names)

    def test_stage_normalization_rejects_conflicting_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "Legacy.php"
            target = root / "legacy.php"
            write(source, "legacy")
            if os.name == "nt":
                target = root / "different.php"
            write(target, "different")

            with self.assertRaisesRegex(RuntimeError, "Conflicting lowercase"):
                publish_notion.merge_lowercase_path(source, target)

    def test_first_notion_image_url_accepts_uploaded_file(self):
        blocks = [
            {"type": "paragraph", "paragraph": {}},
            {
                "type": "image",
                "image": {
                    "type": "file",
                    "file": {"url": "https://notion.example/cover.jpg"},
                },
            },
        ]

        self.assertEqual(
            "https://notion.example/cover.jpg",
            publish_notion.first_notion_image_url(blocks),
        )

    def test_notion_cover_target_reuses_title_cased_source_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            title_cased = (
                source
                / "Root/Resource/World/Philosophy/Hindu/Hindu_Atheist/Index.jpg"
            )
            write(title_cased, "cover")

            target = publish_notion.notion_cover_target(
                source, "world/philosophy/hindu/hindu_atheist"
            )

            self.assertEqual(title_cased, target)

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

    def test_queued_link_to_existing_public_page_is_allowed(self):
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
            metadata["queued_slugs"] = ["world/example", "world/philosophy/cognition"]
            write(metadata_path, json.dumps(metadata))
            write(
                public_repo / "public/world/philosophy/cognition/index.html",
                "Cognition",
            )
            stage = Path(temp_dir) / "stage"
            write(stage / "public/world/example/index.html", "Example")
            write(
                stage / "public/world/example/index.json",
                json.dumps(
                    {
                        "desc": "Description",
                        "content": "Read /world/philosophy/cognition next",
                    }
                ),
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

    def test_queued_link_to_missing_public_page_is_rejected(self):
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
            metadata["queued_slugs"] = ["world/example", "world/philosophy/cognition"]
            write(metadata_path, json.dumps(metadata))
            stage = Path(temp_dir) / "stage"
            write(stage / "public/world/example/index.html", "Example")
            write(
                stage / "public/world/example/index.json",
                json.dumps(
                    {
                        "desc": "Description",
                        "content": "Read /world/philosophy/cognition next",
                    }
                ),
            )
            write(stage / "public/world/example/index.jpg", "cover")

            with self.assertRaisesRegex(RuntimeError, "world/philosophy/cognition"):
                publish_notion.publish_artifacts(
                    SimpleNamespace(
                        metadata=str(metadata_path),
                        stage=str(stage),
                        public_repo=str(public_repo),
                        base_url="https://ujnotes.com",
                    )
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
            write(
                stage / "public/world/example/index.html",
                "<html><script src=/script-123.min.js></script>Example</html>",
            )
            write(stage / "public/script-123.min.js", "window.example = true;")
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
            self.assertEqual(
                "window.example = true;",
                (
                    public_repo / "public/script-123.min.js"
                ).read_text(encoding="utf-8"),
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertIn(
                "public/script-123.min.js", metadata["public_paths"]
            )
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
            write(
                stage / "public/world/example/index.html",
                "<html><script src=/script-123.min.js></script>Example</html>",
            )
            write(stage / "public/script-123.min.js", "window.example = true;")
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

    def test_nested_translation_bundle_is_published_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle, source, public_repo, metadata_path = self.make_fixture(temp_dir)
            slug = "world/example"
            write(
                bundle / "HTML/Component/hi/world/example/index.php",
                "<div id='message'>उदाहरण</div>",
            )
            write(
                bundle / "Config/ID_hi.tsv",
                "Status\tId\tLabel\tTitle\tJS\tDescription\tType\n"
                "publish\tworld/example\tउदाहरण\tहिंदी उदाहरण\t0\tहिंदी विवरण\tarticle\n",
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["variants"] = [
                {
                    "slug": slug,
                    "title": "Example",
                    "description": "Description",
                    "language": "en",
                    "component": "HTML/Component/world/example/index.php",
                },
                {
                    "slug": slug,
                    "title": "हिंदी उदाहरण",
                    "description": "हिंदी विवरण",
                    "language": "hi",
                    "component": "HTML/Component/hi/world/example/index.php",
                },
            ]
            write(metadata_path, json.dumps(metadata, ensure_ascii=False))

            publish_notion.prepare_source(
                SimpleNamespace(
                    bundle=str(bundle),
                    metadata=str(metadata_path),
                    source=str(source),
                    base_url="https://ujnotes.com",
                )
            )
            prepared = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [
                    "Root/HTML/Component/world/example/index.php",
                    "Root/HTML/Component/hi/world/example/index.php",
                ],
                prepared["source_components"],
            )
            hindi_id = (source / "Config/ID_hi.tsv").read_text(encoding="utf-8")
            self.assertIn(
                "published\tworld/example\tउदाहरण\tहिंदी उदाहरण",
                hindi_id,
            )
            translations = (
                source / "Config/Translations.tsv"
            ).read_text(encoding="utf-8")
            self.assertEqual(
                "TranslationGroup\ten\thi\n"
                "world/example\tpublished\tpublished\n",
                translations,
            )
            self.assertIn(
                "https://ujnotes.com/hi/world/example",
                (source / "Root/Site/SiteMap.xml").read_text(encoding="utf-8"),
            )

            stage = Path(temp_dir) / "stage"
            publish_notion.create_stage(
                SimpleNamespace(
                    metadata=str(metadata_path),
                    source=str(source),
                    stage=str(stage),
                )
            )
            self.assertEqual(
                ["world/example", "hi/world/example"],
                (stage / "Config/Render.lsv")
                .read_text(encoding="utf-8")
                .splitlines(),
            )
            write(
                stage / "public/world/example/index.html",
                "<html>Example</html>",
            )
            write(
                stage / "public/world/example/index.json",
                json.dumps({"desc": "Description", "content": "Example"}),
            )
            write(
                stage / "public/hi/world/example/index.html",
                "<html>उदाहरण</html>",
            )
            write(
                stage / "public/hi/world/example/index.json",
                json.dumps(
                    {"desc": "हिंदी विवरण", "content": "उदाहरण"},
                    ensure_ascii=False,
                ),
            )

            publish_notion.publish_artifacts(
                SimpleNamespace(
                    metadata=str(metadata_path),
                    stage=str(stage),
                    public_repo=str(public_repo),
                    base_url="https://ujnotes.com",
                )
            )

            published = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"world/example", "hi/world/example"},
                set(published["variant_hashes"]),
            )
            firebase = json.loads(
                (public_repo / "firebase.json").read_text(encoding="utf-8")
            )["hosting"]
            self.assertIn(
                {
                    "source": "/hi/world/example.json",
                    "destination": "/hi/world/example/index.json",
                },
                firebase["rewrites"],
            )
            self.assertTrue(
                (
                    public_repo
                    / "public/hi/world/example/index.json"
                ).is_file()
            )


    def test_root_translation_preserves_code_native_english_component(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle, source, _, metadata_path = self.make_fixture(temp_dir)
            slug = "root"
            write(
                bundle / "HTML/Component/root/index.php",
                "<div id='message'>Generated root</div>",
            )
            write(
                bundle / "HTML/Component/hi/root/index.php",
                "<div id='message'>हिन्दी मुखपृष्ठ</div>\n"
                "<?php require('../JS/Base/page.js'); ?>\n"
                "<?php require('../HTML/Fragment/Component_bottom.php') ?>",
            )
            write(
                bundle / "Config/ID.tsv",
                "Status\tId\tLabel\tTitle\tJS\tDescription\tType\n"
                "publish\troot\tUjnotes\tUjnotes\t1\tDescription\tpage\n",
            )
            write(
                bundle / "Config/ID_hi.tsv",
                "Status\tId\tLabel\tTitle\tJS\tDescription\tType\n"
                "publish\troot\tउज नोट्स\tउज नोट्स\t1\tविवरण\tpage\n",
            )
            native_root = "<?php require_once 'Fragment/Item_text.php'; ?>\n"
            write(source / "Root/HTML/Component/Root.php", native_root)
            metadata = {
                "page_id": "page-root",
                "slug": slug,
                "title": "Ujnotes",
                "description": "Description",
                "language": "en",
                "component": "HTML/Component/root/index.php",
                "queued_slugs": [slug],
                "variants": [
                    {
                        "slug": slug,
                        "title": "Ujnotes",
                        "description": "Description",
                        "language": "en",
                        "component": "HTML/Component/root/index.php",
                    },
                    {
                        "slug": slug,
                        "title": "उज नोट्स",
                        "description": "विवरण",
                        "language": "hi",
                        "component": "HTML/Component/hi/root/index.php",
                    },
                ],
            }
            write(metadata_path, json.dumps(metadata, ensure_ascii=False))

            publish_notion.prepare_source(
                SimpleNamespace(
                    bundle=str(bundle),
                    metadata=str(metadata_path),
                    source=str(source),
                    base_url="https://ujnotes.com",
                )
            )

            prepared = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [
                    "Root/HTML/Component/Root.php",
                    "Root/HTML/Component/hi/root/index.php",
                ],
                prepared["source_components"],
            )
            self.assertEqual(
                native_root,
                (source / "Root/HTML/Component/Root.php").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertFalse(
                (source / "Root/HTML/Component/root/index.php").exists()
            )
            hindi_root = source / "Root/HTML/Component/hi/root/index.php"
            self.assertTrue(hindi_root.is_file())
            hindi_root_text = hindi_root.read_text(encoding="utf-8")
            self.assertNotIn("../JS/Base/page.js", hindi_root_text)
            self.assertNotIn("Component_bottom.php", hindi_root_text)

            stage = Path(temp_dir) / "stage"
            publish_notion.create_stage(
                SimpleNamespace(
                    metadata=str(metadata_path),
                    source=str(source),
                    stage=str(stage),
                )
            )
            staged = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [
                    "Root/HTML/Component/root.php",
                    "Root/HTML/Component/hi/root/index.php",
                ],
                staged["source_components"],
            )
            self.assertTrue(
                (stage / "Root/HTML/Component/root.php").is_file()
            )

    def test_renderer_mounts_normalized_stage(self):
        project = Path(__file__).resolve().parents[1]
        compose = (project / "compose-dev.yaml").read_text(encoding="utf-8")
        workflow = (
            project / ".github/workflows/publish-notion.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "source: ${SITE_PROJECT_DIR:-../site/project}", compose
        )
        self.assertIn("target: /app/site/project", compose)
        self.assertIn(
            "SITE_PROJECT_DIR: ${{ github.workspace }}/.ncms-publish/site",
            workflow,
        )
        self.assertIn('ln -s Root "$STAGE_DIR/root"', workflow)
        self.assertIn('["source_paths"]', workflow)
        self.assertIn("paths:\n      - .github/workflows/publish-notion.yml", workflow)
        self.assertIn("      - ci/publish_notion.py", workflow)
        self.assertIn('github.event_name }}" != "workflow_dispatch"', workflow)


if __name__ == "__main__":
    unittest.main()
