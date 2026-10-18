"""Content graph regressions; run with python3 -m unittest discover -s scripts."""

import contextlib
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import prebuild


class ContentGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "data/content"
        self.data = self.root / "data/extracted"
        self.pages = self.root / "content/v1"
        overrides = dict(ROOT=self.root, SRC_CONTENT=self.src,
                         OUT_DATA=self.data, OUT_CONTENT=self.pages)
        self.patcher = patch.multiple(prebuild, **overrides)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def page(self, path, frontmatter="", body=""):
        file = self.src / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f'+++\ntitle = "{file.stem}"\n{frontmatter}\n+++\n{body}', encoding="utf-8")
        return file

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            prebuild.build_graph()
        graph = json.loads((self.data / "graph.json").read_text())
        ids = {n["id"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["source"], ids)
            self.assertIn(edge["target"], ids)
        download = json.loads((self.root / "static/v1/graph/content-graph.json").read_text())
        for key in ("nodes", "edges", "stats", "qa"):
            self.assertEqual(download[key], graph[key])
        xml = ET.parse(self.root / "static/v1/graph/content-graph.graphml")
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        self.assertEqual({n.attrib["id"] for n in xml.findall(".//g:node", ns)}, ids)
        self.assertEqual(
            {(e.attrib["source"], e.attrib["target"], e.find("g:data", ns).text)
             for e in xml.findall(".//g:edge", ns)},
            {(e["source"], e["target"], e["type"]) for e in graph["edges"]})
        return graph

    def test_drafts_excluded_in_every_section_and_incoming_links(self):
        for section in prebuild.GRAPH_SECTIONS:
            self.page(f"{section}/secret.md", 'draft = true\naliases = ["/old-secret/"]' if section == "wiki"
                      else 'draft = true', '{% wiki(slug="visible") %}visible{% end %}')
        self.page("wiki/visible.md", '''[extra]
see_also = [{path = "/wiki/secret/"}, {path = "/articles/secret/"},
            {path = "/timeline/secret/"}, {path = "/news/secret/"}, {path = "/old-secret/"}]
''', '{% wiki(slug="secret") %}secret{% end %}')
        graph = self.build()
        self.assertEqual([n["id"] for n in graph["nodes"]], ["wiki/visible"])
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["qa"]["dangling"], [])
        self.assertEqual(graph["stats"]["excluded_links"], 6)
        self.assertNotIn("secret", json.dumps(graph))
        self.assertEqual(len(list((self.data / "graph_nodes").glob("*.json"))), 1)
        self.assertEqual(len(list((self.pages / "graph").glob("node-*.md"))), 1)

    def test_canonical_alias_and_language_links_share_one_resolution(self):
        self.page("wiki/old.md", 'slug = "canonical"\naliases = ["/wiki/old/", "/intro/old/"]')
        self.page("timeline/age.md", 'aliases = ["/wiki/age/"]')
        self.page("wiki/source.md", '''[extra]
see_also = [{path = "wiki/old"}, {path = "/en/wiki/canonical/"},
            {path = "https://www.wheelofheaven.world/de/wiki/old/?ref=a#section"}]
canon_links = [{path = "/intro/old/"}, {path = "/wiki/age/"}]
''', '{% wiki(slug="old") %}old{% end %}\n{% wiki(slug="canonical") %}canonical{% end %}')
        graph = self.build()
        self.assertEqual(graph["qa"]["dangling"], [])
        self.assertEqual({(e["target"], e["type"]) for e in graph["edges"]},
                         {("wiki/canonical", "see_also"), ("wiki/canonical", "in_body"),
                          ("timeline/age", "see_also")})
        self.assertEqual(len(graph["edges"]), 3)
        ego = json.loads((self.data / "graph_nodes/wiki__source.json").read_text())
        self.assertEqual({n["id"] for n in ego["neighbors"]}, {"wiki/canonical", "timeline/age"})
        self.assertTrue((self.pages / "graph/node-wiki-canonical.md").exists())
        self.assertFalse((self.pages / "graph/node-wiki-old.md").exists())

    def test_missing_vs_verified_outside_graph_vs_unchecked_offsite(self):
        self.page("library/book.md", 'aliases = ["/wiki/book/"]')
        self.page("library/draft.md", 'draft = true')
        self.page("sources/_generated/source.md", 'path = "/sources/source/"')
        self.page("library/_index.md")
        self.page("_index.md")
        self.page("de/library/translated-only.md")
        self.page("wiki/source.md", '''[extra]
see_also = [{path = "/library/book/"}, {path = "/sources/source/"},
            {path = "/library/"}, {path = "/"}, {path = "/library/absent/"},
            {path = "/wiki/absent/"}, {path = "/wiki/source/not-a-page/"},
            {path = "/library/translated-only/"}, {path = "/library/draft/"},
            {path = "https://elsewhere.example/wiki/source/"}]
''', '{% wiki(slug="book") %}book{% end %}')
        graph = self.build()
        self.assertEqual(graph["stats"]["outside_graph_links"], 5)
        self.assertEqual(graph["stats"]["dangling_links"], 4)
        self.assertEqual(graph["stats"]["external_links"], 1)
        self.assertEqual(graph["stats"]["excluded_links"], 1)
        self.assertEqual({d["reason"] for d in graph["qa"]["dangling"]}, {"internal_missing"})
        self.assertEqual(graph["edges"], [])

    def test_slug_override_does_not_invent_a_filename_alias(self):
        self.page("wiki/old.md", 'slug = "new"')
        self.page("wiki/source.md", body='{% wiki(slug="old") %}old{% end %}')
        graph = self.build()
        self.assertEqual(graph["qa"]["dangling"], [dict(source="wiki/source", path="wiki/old",
                                                       reason="internal_missing", via="in_body")])

    def test_self_links_and_repeated_aliases_do_not_inflate_degrees(self):
        self.page("wiki/node.md", '''aliases = ["/wiki/old/"]
[extra]
see_also = [{path = "/wiki/old/"}, {path = "/wiki/node/"}]
''', '{% wiki(slug="old") %}old{% end %}')
        graph = self.build()
        self.assertEqual(graph["nodes"][0]["degree"], dict(out=0, **{"in": 0}, total=0))
        self.assertEqual(graph["edges"], [])

    def test_conflicting_aliases_fail_instead_of_silently_choosing_a_node(self):
        self.page("wiki/first.md", 'aliases = ["/wiki/shared/"]')
        self.page("wiki/second.md", 'aliases = ["/wiki/shared/"]')
        with self.assertRaisesRegex(ValueError, "Ambiguous graph destination /wiki/shared/"):
            self.build()

    def test_rebuild_removes_drafted_deleted_and_renamed_artifacts(self):
        self.page("wiki/visible.md", '[extra]\nsee_also = [{path = "/articles/secret/"}]')
        self.page("articles/secret.md", body='{% wiki(slug="visible") %}visible{% end %}')
        deleted = self.page("news/deleted.md")
        self.page("timeline/old.md")
        self.build()
        public = self.root / "public/v1/graph/articles/secret"
        public.mkdir(parents=True)
        (public / "index.html").write_text("previously published draft")
        (public / "index.json").write_text("legacy explicit endpoint")
        sibling = self.root / "public/v1/keep.txt"
        sibling.write_text("unrelated output")
        self.page("articles/secret.md", 'draft = true')
        deleted.unlink()
        self.page("timeline/old.md", 'slug = "new"')
        self.build()
        self.assertFalse(public.exists())
        self.assertEqual(sibling.read_text(), "unrelated output")
        for folder in (self.pages / "graph", self.data / "graph_nodes", self.root / "static/v1/graph"):
            for file in folder.iterdir():
                self.assertNotIn("secret", file.name)
                self.assertNotIn("secret", file.read_text())
                self.assertNotIn("deleted", file.read_text())
                self.assertNotIn("timeline/old", file.read_text())
        self.assertTrue((self.pages / "graph/node-timeline-new.md").exists())
        # Removing a whole source section must clear its previous ego pages too.
        for file in self.src.rglob("*.md"):
            file.unlink()
        graph = self.build()
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(list((self.data / "graph_nodes").iterdir()), [])
        self.assertEqual(list((self.pages / "graph").glob("node-*.md")), [])


if __name__ == "__main__":
    unittest.main()
