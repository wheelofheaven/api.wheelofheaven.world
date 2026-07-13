#!/usr/bin/env python3
"""Pre-build for api.wheelofheaven.world.

Extracts content from the data submodules (data/content, data/library)
into Zola content files and per-section index data files. Each section
gets:

- `data/extracted/{section}.json`  — the lightweight index consumed by
  the listing endpoint (e.g. /v1/wiki/).
- `content/v1/{section}/{slug}.md` — one Zola page per entry. Zola
  renders its body as HTML and the per-entry template emits the JSON
  for /v1/{section}/{slug}/.

The generated `content/v1/{section}/{slug}.md` files are gitignored —
they are derived artifacts of data/content. Section `_index.md` files
under content/v1/ are committed and define section-level config.

Run via `mise run build` (chained before zola) or manually:
    python scripts/prebuild.py
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class _JSONEncoder(json.JSONEncoder):
    """JSON encoder that serialises date/datetime as ISO strings."""

    def default(self, o: Any) -> Any:  # noqa: D401
        if isinstance(o, _dt.datetime):
            return o.isoformat()
        if isinstance(o, _dt.date):
            return o.isoformat()
        return super().default(o)


def _dumps(obj: Any, **kw: Any) -> str:
    return json.dumps(obj, cls=_JSONEncoder, **kw)

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover - py3.10 fallback
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
SRC_CONTENT = ROOT / "data" / "content"
SRC_LIBRARY = ROOT / "data" / "library"
SRC_BIBLIOGRAPHY = ROOT / "data" / "bibliography"
OUT_DATA = ROOT / "data" / "extracted"
OUT_CONTENT = ROOT / "content" / "v1"

DEFAULT_LANG = "en"
# Non-default languages with content directories in data/content/{lang}/.
EXTRA_LANGS = ("de", "es", "fr", "ja", "ko", "ru", "zh", "zh-Hant", "he")

FRONTMATTER_RE = re.compile(r"^\s*\+\+\+\s*\n(.*?)\n\+\+\+\s*\n?", re.DOTALL)

# Keys lifted from `[extra]` (or top-level) into the index entry.
INDEX_KEYS = (
    "category",
    "claim_type",
    "editorial_pass",
    "translation_status",
    "alternative_names",
    "featured_order",
    "weight",
    "symbol",
    "start_year",
    "end_year",
    "zodiac_sign",
    "color",
    "genesis_day",
    "event_date",
    "event_type",
)


def parse_toml_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.lstrip().startswith("+++"):
        return {}, raw
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    try:
        fm = tomllib.loads(m.group(1))
    except tomllib.TOMLDecodeError as exc:
        print(f"  TOML parse error: {exc}", file=sys.stderr)
        return {}, raw
    return fm, raw[m.end():]


_TEMPLATE_LINE_RE = re.compile(r'^template\s*=\s*"[^"]*"\s*$', re.MULTILINE)
_TOC_LINE_RE = re.compile(r'^toc\s*=\s*(true|false)\s*$', re.MULTILINE)
_ALIASES_LINE_RE = re.compile(r'^aliases\s*=\s*\[[^\]]*\]\s*$', re.MULTILINE)
_EXTRA_WEIGHT_RE = re.compile(r'^(weight\s*=\s*-?\d+\s*)$', re.MULTILINE)


def _promote_weight_to_toplevel(fm_block: str, fm_dict: dict) -> str:
    """If `weight` lives under [extra] in the source, promote a top-level
    copy so Zola's section sort_by="weight" works."""
    extra = fm_dict.get("extra") or {}
    if "weight" not in extra:
        return fm_block
    if re.search(r'^weight\s*=', fm_block, re.MULTILINE):
        return fm_block
    weight_val = extra["weight"]
    if isinstance(weight_val, bool) or not isinstance(weight_val, (int, float)):
        return fm_block
    # Insert as the first line after `+++` (i.e. at the top of the block).
    return f"weight = {int(weight_val)}\n" + fm_block


def patch_frontmatter(raw: str, fm_dict: dict, *, new_template: str) -> str:
    """Patch the original markdown source: replace the template line,
    drop www-only fields, promote weight from [extra] if needed. Keeps
    everything else byte-for-byte so the complex TOML (array-of-tables,
    infoboxes, etc.) round-trips exactly."""
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return raw
    fm_block = m.group(1)
    body = raw[m.end():]

    if _TEMPLATE_LINE_RE.search(fm_block):
        fm_block = _TEMPLATE_LINE_RE.sub(f'template = "{new_template}"', fm_block, count=1)
    else:
        fm_block = fm_block.rstrip() + f'\ntemplate = "{new_template}"\n'
    fm_block = _TOC_LINE_RE.sub("", fm_block)
    fm_block = _ALIASES_LINE_RE.sub("", fm_block)
    fm_block = _promote_weight_to_toplevel(fm_block, fm_dict)
    # Collapse triple newlines introduced by deletions.
    fm_block = re.sub(r"\n{3,}", "\n\n", fm_block)
    return f"+++\n{fm_block}\n+++\n{body}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_generated_pages(directory: Path) -> None:
    """Remove existing generated pages, preserving _index.md."""
    if not directory.exists():
        return
    for path in directory.glob("*.md"):
        if path.name != "_index.md":
            path.unlink()


def _lang_prefix(lang: str) -> str:
    """URL prefix segment for non-default languages."""
    return "" if lang == DEFAULT_LANG else f"/{lang}"


def _ensure_lang_section_index(lang: str, kind: str, *, title: str, template: str, sort_by: str = "title", data_kind: str | None = None) -> None:
    """For non-default languages, write the section _index.md that wires the
    section to the language-aware data path. English _index.md files are
    committed by hand; we don't touch them."""
    if lang == DEFAULT_LANG:
        return
    section_dir = OUT_CONTENT / lang / kind
    section_dir.mkdir(parents=True, exist_ok=True)
    data_kind = data_kind or kind
    body = (
        "+++\n"
        f'title = "{title}"\n'
        f'sort_by = "{sort_by}"\n'
        f'template = "{template}"\n'
        "transparent = true\n"
        "\n"
        "[extra]\n"
        f'lang = "{lang}"\n'
        f'lang_prefix = "{_lang_prefix(lang)}"\n'
        f'data_path = "data/extracted/{lang}/{data_kind}.json"\n'
        "+++\n"
    )
    (section_dir / "_index.md").write_text(body, encoding="utf-8")


def _ensure_lang_root_index(lang: str) -> None:
    """Top-level _index.md for /v1/{lang}/. English root exists already."""
    if lang == DEFAULT_LANG:
        return
    root = OUT_CONTENT / lang
    root.mkdir(parents=True, exist_ok=True)
    body = (
        "+++\n"
        f'title = "Wheel of Heaven API ({lang})"\n'
        'render = false\n'
        "+++\n"
    )
    (root / "_index.md").write_text(body, encoding="utf-8")


def _add_lang_extras(fm_block: str, lang: str) -> str:
    """Inject extra.lang and extra.lang_prefix into the patched
    frontmatter block. Inserts at the [extra] table boundary, or creates
    [extra] if absent."""
    lang_prefix = _lang_prefix(lang)
    if re.search(r"^lang\s*=", fm_block, re.MULTILINE):
        return fm_block
    extra_marker = re.search(r"^\[extra\]\s*$", fm_block, re.MULTILINE)
    inject = f'\nlang = "{lang}"\nlang_prefix = "{lang_prefix}"'
    if extra_marker:
        head = fm_block[: extra_marker.end()]
        tail = fm_block[extra_marker.end():]
        return head + inject + tail
    # No [extra] section — append one.
    return fm_block.rstrip() + f"\n\n[extra]{inject}\n"


def process_section(
    *,
    kind: str,
    src_subdir: str,
    page_template: str,
    lang: str = DEFAULT_LANG,
) -> int:
    """Process one content section in one language.

    Reads {data/content,data/content/{lang}}/{src_subdir}/*.md, emits one
    Zola page per entry and a section index file at
    data/extracted/{lang}/{kind}.json (or data/extracted/{kind}.json for
    the default language).
    """
    src_root = SRC_CONTENT if lang == DEFAULT_LANG else SRC_CONTENT / lang
    src = src_root / src_subdir
    if not src.exists():
        return 0

    dest_pages = OUT_CONTENT / kind if lang == DEFAULT_LANG else OUT_CONTENT / lang / kind
    dest_pages.mkdir(parents=True, exist_ok=True)
    clean_generated_pages(dest_pages)

    entries: list[dict] = []

    for md_file in sorted(src.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        raw = md_file.read_text(encoding="utf-8")
        fm, body = parse_toml_frontmatter(raw)
        if not fm.get("title"):
            continue

        slug = fm.get("slug") or md_file.stem

        patched = patch_frontmatter(raw, fm, new_template=page_template)
        # Inject lang/lang_prefix into the patched frontmatter block.
        m = FRONTMATTER_RE.match(patched)
        if m:
            new_block = _add_lang_extras(m.group(1), lang)
            patched = f"+++\n{new_block}\n+++\n{patched[m.end():]}"

        (dest_pages / f"{slug}.md").write_text(patched, encoding="utf-8")

        lang_prefix = _lang_prefix(lang)
        index_entry: dict = {
            "slug": slug,
            "title": fm.get("title", ""),
            "description": fm.get("description", ""),
            "url": f"/v1{lang_prefix}/{kind}/{slug}/",
        }
        extra = fm.get("extra") or {}
        for key in INDEX_KEYS:
            if key in extra:
                index_entry[key] = extra[key]
            elif key in fm:
                index_entry[key] = fm[key]
        if "weight" in fm and "weight" not in index_entry:
            index_entry["weight"] = fm["weight"]
        entries.append(index_entry)

    if any("weight" in e for e in entries):
        entries.sort(key=lambda e: (e.get("weight", 999), e.get("title", "").lower()))
    else:
        entries.sort(key=lambda e: e.get("title", "").lower())

    data_path = OUT_DATA / f"{kind}.json" if lang == DEFAULT_LANG else OUT_DATA / lang / f"{kind}.json"
    write_json(
        data_path,
        {
            "version": "1.0",
            "generated": now_iso(),
            "language": lang,
            "count": len(entries),
            "entries": entries,
        },
    )
    if entries:
        print(f"  [{lang}] {kind}: {len(entries)} entries -> {dest_pages.relative_to(ROOT)}/")
    return len(entries)


def process_traditions() -> int:
    """Tradition hubs live one level deeper: data/content/sources/tradition/."""
    src = SRC_CONTENT / "sources" / "tradition"
    if not src.exists():
        print("  traditions: source dir missing; skipping")
        return 0
    dest_pages = OUT_CONTENT / "sources" / "traditions"
    dest_pages.mkdir(parents=True, exist_ok=True)
    clean_generated_pages(dest_pages)

    entries: list[dict] = []
    for md_file in sorted(src.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        raw = md_file.read_text(encoding="utf-8")
        fm, body = parse_toml_frontmatter(raw)
        if not fm.get("title"):
            continue
        slug = fm.get("slug") or md_file.stem
        (dest_pages / f"{slug}.md").write_text(
            patch_frontmatter(raw, fm, new_template="v1-tradition-page.json"),
            encoding="utf-8",
        )

        entry = {
            "slug": slug,
            "title": fm.get("title", ""),
            "description": fm.get("description", ""),
            "url": f"/v1/sources/traditions/{slug}/",
        }
        extra = fm.get("extra") or {}
        for key in ("source_family", "claim_type", "translation_status"):
            if key in extra:
                entry[key] = extra[key]
        entries.append(entry)

    entries.sort(key=lambda e: e.get("title", "").lower())
    write_json(
        OUT_DATA / "traditions_hubs.json",
        {
            "version": "1.0",
            "generated": now_iso(),
            "count": len(entries),
            "entries": entries,
        },
    )
    print(f"  tradition hubs: {len(entries)} entries -> {dest_pages.relative_to(ROOT)}/")
    return len(entries)


def process_translations() -> int:
    """Scan data/library/* for -woh translations and produce index + per-entry stubs."""
    if not SRC_LIBRARY.exists():
        print("  translations: library missing; skipping")
        return 0

    dest_pages = OUT_CONTENT / "translations"
    dest_pages.mkdir(parents=True, exist_ok=True)
    for path in dest_pages.glob("*.md"):
        if path.name != "_index.md":
            path.unlink()

    entries: list[dict] = []
    for path in sorted(SRC_LIBRARY.iterdir()):
        if not path.is_dir() or not path.name.endswith("-woh"):
            continue
        meta_path = path / "_meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slug = meta.get("slug") or path.name
        title = (meta.get("titles") or {}).get("en") or slug
        entries.append(
            {
                "slug": slug,
                "title": title,
                "code": meta.get("code", ""),
                "originalLang": meta.get("originalLang", ""),
                "primaryLang": meta.get("primaryLang", "en"),
                "chapterCount": meta.get("chapterCount", 0),
                "url": f"/v1/translations/{slug}/",
                "library_url": f"/v1/library/books/{slug}/",
            }
        )

        stub = (
            "+++\n"
            f"title = {_dumps(title)}\n"
            f'slug = "{slug}"\n'
            'template = "v1-translation-page.json"\n'
            "+++\n"
        )
        (dest_pages / f"{slug}.md").write_text(stub, encoding="utf-8")

    entries.sort(key=lambda e: e["slug"])
    write_json(
        OUT_DATA / "translations.json",
        {
            "version": "1.0",
            "generated": now_iso(),
            "count": len(entries),
            "entries": entries,
        },
    )
    print(f"  translations: {len(entries)} entries -> {dest_pages.relative_to(ROOT)}/")
    return len(entries)


def process_sources() -> int:
    """Mirror data-bibliography into per-source content stubs and the index.

    /v1/sources/{id}/ is one stub per source record; /v1/sources/ is the
    flat index loaded directly from data/bibliography/index.json.
    """
    if not SRC_BIBLIOGRAPHY.exists():
        print("  sources: data/bibliography missing; skipping")
        return 0
    sources_dir = SRC_BIBLIOGRAPHY / "sources"
    if not sources_dir.exists():
        print("  sources: data/bibliography/sources missing; skipping")
        return 0

    dest_pages = OUT_CONTENT / "sources"
    dest_pages.mkdir(parents=True, exist_ok=True)
    # Clean any prior generated source pages (preserve _index.md and the traditions/ subdir).
    for path in dest_pages.glob("*.md"):
        if path.name != "_index.md":
            path.unlink()

    index_path = SRC_BIBLIOGRAPHY / "index.json"
    index_data: list[dict] = []
    if index_path.exists():
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index_data = []

    count = 0
    for src_file in sorted(sources_dir.glob("*.json")):
        src_id = src_file.stem
        # Render a content stub binding the URL to the per-source template.
        stub = (
            "+++\n"
            f'title = "{src_id}"\n'
            f'slug = "{src_id}"\n'
            'template = "v1-source-page.json"\n'
            "+++\n"
        )
        (dest_pages / f"{src_id}.md").write_text(stub, encoding="utf-8")
        count += 1

    # Mirror the index into data/extracted so the /v1/sources/ template can load_data it.
    write_json(
        OUT_DATA / "sources.json",
        {
            "version": "1.0",
            "generated": now_iso(),
            "count": len(index_data),
            "entries": index_data,
        },
    )
    print(f"  sources: {count} entries -> {dest_pages.relative_to(ROOT)}/")
    return count


def process_library(lang: str = DEFAULT_LANG) -> int:
    """Generate the library-prefixed content tree from data/library/catalog.json
    and per-book chapter files, for one language.

    For every book in the catalog, emit:
      content/v1{lang_dir}/library/books/{slug}/_index.md          (Book detail section)
      content/v1{lang_dir}/library/books/{slug}/meta.md            (BookMeta page)
      content/v1{lang_dir}/library/books/{slug}/chapters/_index.md (ChapterList section)
      content/v1{lang_dir}/library/books/{slug}/chapters/{n}.md    (one per chapter)

    For every tradition in the catalog, emit:
      content/v1{lang_dir}/library/traditions/{slug}.md            (Tradition page)

    The library-prefixed paths are canonical. The legacy /v1/books/,
    /v1/catalog/, /v1/traditions/ surfaces remain live as aliases.
    For non-default languages, the tree is mirrored under /v1/{lang}/library/.
    """
    catalog_path = SRC_LIBRARY / "catalog.json"
    if not catalog_path.exists():
        print(f"  [{lang}] library: catalog.json missing; skipping")
        return 0
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  [{lang}] library: catalog.json parse error: {exc}", file=sys.stderr)
        return 0

    lang_prefix = _lang_prefix(lang)
    library_root = OUT_CONTENT / "library" if lang == DEFAULT_LANG else OUT_CONTENT / lang / "library"
    books_root = library_root / "books"
    traditions_root = library_root / "traditions"
    books_root.mkdir(parents=True, exist_ok=True)
    traditions_root.mkdir(parents=True, exist_ok=True)

    # For non-default langs, emit the section _index.md stubs that bind
    # /v1/{lang}/library, /v1/{lang}/library/books, and
    # /v1/{lang}/library/traditions to their templates with lang extras.
    if lang != DEFAULT_LANG:
        (library_root / "_index.md").write_text(
            "+++\n"
            f'title = "Library ({lang})"\n'
            'template = "v1-library-index.json"\n'
            "transparent = true\n"
            "\n"
            "[extra]\n"
            f'lang = "{lang}"\n'
            f'lang_prefix = "{lang_prefix}"\n'
            "+++\n",
            encoding="utf-8",
        )
        (books_root / "_index.md").write_text(
            "+++\n"
            f'title = "Library Books ({lang})"\n'
            'template = "v1-library-books-index.json"\n'
            "transparent = true\n"
            "\n"
            "[extra]\n"
            f'lang = "{lang}"\n'
            f'lang_prefix = "{lang_prefix}"\n'
            "+++\n",
            encoding="utf-8",
        )
        (traditions_root / "_index.md").write_text(
            "+++\n"
            f'title = "Library Traditions ({lang})"\n'
            'template = "v1-library-traditions-index.json"\n'
            "transparent = true\n"
            "\n"
            "[extra]\n"
            f'lang = "{lang}"\n'
            f'lang_prefix = "{lang_prefix}"\n'
            "+++\n",
            encoding="utf-8",
        )

    # Clean previously generated per-book directories (preserve the
    # committed _index.md at the books-root level for the English tree).
    for path in books_root.iterdir():
        if path.is_dir():
            # Wipe the subtree — it'll be regenerated below.
            for sub in path.rglob("*"):
                if sub.is_file():
                    sub.unlink()
            for sub in sorted(path.rglob("*"), reverse=True):
                if sub.is_dir():
                    sub.rmdir()
            path.rmdir()

    # Per-tradition pages. For the default language we wipe any prior
    # tradition stubs; for non-default langs the directory only contains
    # the just-written _index.md plus our about-to-be-written stubs.
    for path in traditions_root.glob("*.md"):
        if path.name != "_index.md":
            path.unlink()
    for tradition in catalog.get("traditions", []):
        tid = tradition.get("id")
        if not tid:
            continue
        name = (tradition.get("name") or {}).get(lang) or (tradition.get("name") or {}).get("en") or tid
        stub = (
            "+++\n"
            f"title = {_dumps(name)}\n"
            f'template = "v1-library-tradition.json"\n'
            "\n"
            "[extra]\n"
            f'tradition_id = "{tid}"\n'
            f'lang = "{lang}"\n'
            f'lang_prefix = "{lang_prefix}"\n'
            "+++\n"
        )
        (traditions_root / f"{tid}.md").write_text(stub, encoding="utf-8")

    book_count = 0
    chapter_count = 0
    for book in catalog.get("books", []):
        slug = book.get("slug")
        if not slug:
            continue
        # For non-default languages, only emit books that have translation
        # coverage in {lang}. Per-language listings are honest about
        # coverage; for the full corpus, hit the English tree.
        available = book.get("availableLangs") or []
        if lang != DEFAULT_LANG and lang not in available:
            continue
        titles = book.get("titles") or {}
        title = titles.get(lang) or titles.get("en") or slug

        book_dir = books_root / slug
        book_dir.mkdir(parents=True, exist_ok=True)

        # Book detail section (URL: /v1{lang_prefix}/library/books/{slug}/).
        book_index_md = (
            "+++\n"
            f"title = {_dumps(title)}\n"
            'template = "v1-library-book.json"\n'
            'transparent = true\n'
            "\n"
            "[extra]\n"
            f'book_slug = "{slug}"\n'
            f'lang = "{lang}"\n'
            f'lang_prefix = "{lang_prefix}"\n'
            "+++\n"
        )
        (book_dir / "_index.md").write_text(book_index_md, encoding="utf-8")

        # Book meta page (URL: /v1{lang_prefix}/library/books/{slug}/meta/).
        meta_md = (
            "+++\n"
            f"title = {_dumps(title + ' (meta)')}\n"
            'template = "v1-library-book-meta.json"\n'
            "\n"
            "[extra]\n"
            f'book_slug = "{slug}"\n'
            f'lang = "{lang}"\n'
            f'lang_prefix = "{lang_prefix}"\n'
            "+++\n"
        )
        (book_dir / "meta.md").write_text(meta_md, encoding="utf-8")

        # Chapters section (URL: /v1{lang_prefix}/library/books/{slug}/chapters/).
        chapters_dir = book_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        chapters_index_md = (
            "+++\n"
            f"title = {_dumps(title + ' (chapters)')}\n"
            'template = "v1-library-chapters-index.json"\n'
            'transparent = true\n'
            "\n"
            "[extra]\n"
            f'book_slug = "{slug}"\n'
            f'lang = "{lang}"\n'
            f'lang_prefix = "{lang_prefix}"\n'
            "+++\n"
        )
        (chapters_dir / "_index.md").write_text(chapters_index_md, encoding="utf-8")

        # Per-chapter pages.
        n_chapters = int(book.get("chapters") or 0)
        for n in range(1, n_chapters + 1):
            chapter_md = (
                "+++\n"
                f"title = {_dumps(title + ' c' + str(n))}\n"
                'template = "v1-library-chapter.json"\n'
                "\n"
                "[extra]\n"
                f'book_slug = "{slug}"\n'
                f"chapter = {n}\n"
                f'lang = "{lang}"\n'
                f'lang_prefix = "{lang_prefix}"\n'
                "+++\n"
            )
            (chapters_dir / f"{n}.md").write_text(chapter_md, encoding="utf-8")
            chapter_count += 1

        book_count += 1

    print(f"  [{lang}] library: {book_count} books, {chapter_count} chapter pages, "
          f"{len(catalog.get('traditions', []))} traditions "
          f"-> {books_root.relative_to(ROOT)}/")
    return book_count


def process_glossary() -> int:
    """Copy data/content/i18n/glossary.json + per-term stubs."""
    src = SRC_CONTENT / "i18n" / "glossary.json"
    if not src.exists():
        print("  glossary: source missing; skipping")
        return 0
    raw = json.loads(src.read_text(encoding="utf-8"))
    out = {
        "version": "1.0",
        "generated": now_iso(),
        "source": raw,
    }
    write_json(OUT_DATA / "glossary.json", out)

    dest_pages = OUT_CONTENT / "glossary"
    dest_pages.mkdir(parents=True, exist_ok=True)
    for path in dest_pages.glob("*.md"):
        if path.name != "_index.md":
            path.unlink()

    terms = raw.get("terms") or raw.get("entries") or []
    if isinstance(terms, list):
        for term in terms:
            term_id = term.get("id")
            if not term_id:
                continue
            title = (term.get("translations") or {}).get("en") or term_id
            stub = (
                "+++\n"
                f"title = {_dumps(title)}\n"
                f'slug = "{term_id}"\n'
                'template = "v1-glossary-page.json"\n'
                "+++\n"
            )
            (dest_pages / f"{term_id}.md").write_text(stub, encoding="utf-8")
        print(f"  glossary: {len(terms)} terms -> {dest_pages.relative_to(ROOT)}/")
    else:
        print("  glossary: terms not a list; index only")
    return 1


# ---------------------------------------------------------------------------
# Content graph (Decision 15, G2 — see the wheelofheaven repo
# .claude/plans/strategy-distribution-2026.md §"The graph / relatedness
# surface"). Builds a typed graph over the English content nodes
# (wiki/articles/timeline/news) from curated see_also/canon_links edges plus
# in-body {% wiki(slug="...") %} cross-links, and emits:
#   data/extracted/graph.json                     — the full graph (the dataset)
#   data/extracted/graph_nodes/{sec}__{slug}.json — per-node ego networks
#   content/v1/graph/ pages                        — /v1/graph/ + /v1/graph/{sec}/{slug}/
# plus an orphan / asymmetric-see_also QA report (printed + embedded in data.qa).
# ---------------------------------------------------------------------------

GRAPH_SECTIONS = ("wiki", "articles", "timeline", "news")
GRAPH_SECTION_KIND = {
    "wiki": "WikiEntry",
    "articles": "Article",
    "timeline": "TimelineEntry",
    "news": "NewsArticle",
}
_GRAPH_LANG_CODES = {"en", "de", "es", "fr", "ja", "ko", "ru", "zh", "zh-Hant", "he"}
_WIKI_SHORTCODE_RE = re.compile(r'\{%\s*wiki\(\s*slug\s*=\s*"([a-z0-9-]+)"\s*\)\s*%\}')


def _graph_resolve(path: str, nodes: dict) -> tuple[str | None, str]:
    """Resolve a see_also/canon_link path to a node id.

    Returns (node_id, status): 'ok' (internal, resolved), 'internal_missing'
    (content section but unknown slug — a broken link), or 'external' (points
    outside the content graph, e.g. library/sources). A redundant leading
    language segment is tolerated (see project_see_also_langprefix_bug)."""
    segs = [s for s in path.strip().strip("/").split("/") if s]
    if segs and segs[0] in _GRAPH_LANG_CODES:
        segs = segs[1:]
    if len(segs) >= 2 and segs[0] in GRAPH_SECTIONS:
        nid = f"{segs[0]}/{segs[1]}"
        return (nid, "ok") if nid in nodes else (None, "internal_missing")
    return (None, "external")


def build_graph() -> None:
    nodes: dict[str, dict] = {}
    curated: dict[str, list] = {}
    bodies: dict[str, str] = {}

    for section in GRAPH_SECTIONS:
        d = SRC_CONTENT / section
        if not d.exists():
            continue
        for md in sorted(d.glob("*.md")):
            if md.name == "_index.md":
                continue
            fm, body = parse_toml_frontmatter(md.read_text(encoding="utf-8"))
            if not fm.get("title"):
                continue
            slug = fm.get("slug") or md.stem
            nid = f"{section}/{slug}"
            extra = fm.get("extra") or {}
            nodes[nid] = {
                "id": nid,
                "section": section,
                "slug": slug,
                "kind": GRAPH_SECTION_KIND[section],
                "title": fm.get("title", ""),
                "url": f"/v1/{section}/{slug}/",
                "graph_url": f"/v1/graph/{section}/{slug}/",
                "claim_type": extra.get("claim_type", ""),
                "category": extra.get("category", ""),
            }
            curated[nid] = list(extra.get("see_also") or []) + list(extra.get("canon_links") or [])
            bodies[nid] = body

    edges: list[dict] = []
    seen: set = set()
    dangling: list[dict] = []

    def add_edge(s: str, t: str, ty: str) -> None:
        key = (s, t, ty)
        if key in seen or s == t:
            return
        seen.add(key)
        edges.append({"source": s, "target": t, "type": ty})

    for nid in nodes:
        for item in curated.get(nid, []):
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not path:
                continue
            tid, status = _graph_resolve(path, nodes)
            if status == "ok":
                add_edge(nid, tid, "see_also")
            else:
                dangling.append({"source": nid, "path": path, "reason": status, "via": "see_also"})
        for m in _WIKI_SHORTCODE_RE.finditer(bodies.get(nid, "")):
            tid = f"wiki/{m.group(1)}"
            if tid in nodes:
                add_edge(nid, tid, "in_body")
            else:
                dangling.append({"source": nid, "path": tid, "reason": "internal_missing", "via": "in_body"})

    out_deg = {nid: 0 for nid in nodes}
    in_deg = {nid: 0 for nid in nodes}
    for e in edges:
        out_deg[e["source"]] += 1
        in_deg[e["target"]] += 1
    for nid, n in nodes.items():
        n["degree"] = {"out": out_deg[nid], "in": in_deg[nid], "total": out_deg[nid] + in_deg[nid]}

    see_pairs = {(e["source"], e["target"]) for e in edges if e["type"] == "see_also"}
    asymmetric = [{"from": s, "to": t} for (s, t) in sorted(see_pairs) if (t, s) not in see_pairs]
    orphans = sorted(nid for nid in nodes if nodes[nid]["degree"]["total"] == 0)

    by_kind: dict = {}
    for n in nodes.values():
        by_kind[n["kind"]] = by_kind.get(n["kind"], 0) + 1
    by_type: dict = {}
    for e in edges:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    graph = {
        "generated": now_iso(),
        "language": DEFAULT_LANG,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "nodes_by_kind": by_kind,
            "edges_by_type": by_type,
            "orphans": len(orphans),
            "asymmetric_see_also": len(asymmetric),
            "dangling_links": len(dangling),
        },
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": edges,
        "qa": {
            "orphans": orphans,
            "asymmetric_see_also": asymmetric,
            "dangling": sorted(dangling, key=lambda d: (d["source"], d["path"])),
        },
    }
    write_json(OUT_DATA / "graph.json", graph)
    _write_graph_datasets(graph)

    ego_dir = OUT_DATA / "graph_nodes"
    if ego_dir.exists():
        for f in ego_dir.glob("*.json"):
            f.unlink()
    ego_dir.mkdir(parents=True, exist_ok=True)

    adj_out: dict = {nid: [] for nid in nodes}
    adj_in: dict = {nid: [] for nid in nodes}
    for e in edges:
        adj_out[e["source"]].append(e)
        adj_in[e["target"]].append(e)

    def _summary(nid: str) -> dict:
        n = nodes[nid]
        return {"id": n["id"], "title": n["title"], "kind": n["kind"],
                "url": n["url"], "graph_url": n["graph_url"]}

    for nid, n in nodes.items():
        neighbor_ids = {e["target"] for e in adj_out[nid]} | {e["source"] for e in adj_in[nid]}
        ego = {
            "generated": now_iso(),
            "language": DEFAULT_LANG,
            "node": n,
            "out": adj_out[nid],
            "in": adj_in[nid],
            "neighbors": [_summary(x) for x in sorted(neighbor_ids)],
        }
        write_json(ego_dir / f'{n["section"]}__{n["slug"]}.json', ego)

    _generate_graph_pages(nodes)

    print(f"  graph: {len(nodes)} nodes, {len(edges)} edges "
          f"({', '.join(f'{k}:{v}' for k, v in sorted(by_type.items()))}) -> content/v1/graph/")
    print(f"  graph QA: {len(orphans)} orphans, {len(asymmetric)} asymmetric see_also, "
          f"{len(dangling)} dangling links")
    if orphans:
        shown = ", ".join(orphans[:12])
        print(f"    orphans: {shown}{' …' if len(orphans) > 12 else ''}")


def _write_graph_datasets(graph: dict) -> None:
    """Packaged, citable dataset downloads (Decision 15, G2). A self-describing
    content-graph.json plus a GraphML twin, emitted as static files served at
    /v1/graph/content-graph.{json,graphml}. Landing page + schema.org/Dataset
    markup live on www at /datasets/content-graph/."""
    dl_dir = ROOT / "static" / "v1" / "graph"
    dl_dir.mkdir(parents=True, exist_ok=True)
    dataset = {
        "name": "Wheel of Heaven Content Graph",
        "description": (
            "A typed relatedness graph over the English Wheel of Heaven corpus "
            "(wiki, articles, timeline, news). Nodes are content resources; edges "
            "are typed (see_also = curated relatedness, in_body = prose cross-link)."
        ),
        "license": "CC0-1.0",
        "landing_page": "https://www.wheelofheaven.world/datasets/content-graph/",
        "api": "https://api.wheelofheaven.world/v1/graph/",
        "schema": "https://api.wheelofheaven.world/v1/schema/content-graph/",
        "generated": graph["generated"],
        "language": graph["language"],
        "stats": graph["stats"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "qa": graph["qa"],
    }
    (dl_dir / "content-graph.json").write_text(
        _dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    (dl_dir / "content-graph.graphml").write_text(_graphml(graph), encoding="utf-8")


def _graphml(graph: dict) -> str:
    """Render the graph as GraphML (for Gephi / network-analysis tools)."""
    from xml.sax.saxutils import escape as _xml_escape

    def esc(s: Any) -> str:
        return _xml_escape(str(s), {'"': "&quot;"})

    node_keys = ("title", "kind", "section", "claim_type", "category", "url")
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
    for k in node_keys:
        out.append(f'  <key id="{k}" for="node" attr.name="{k}" attr.type="string"/>')
    out.append('  <key id="type" for="edge" attr.name="type" attr.type="string"/>')
    out.append('  <graph edgedefault="directed">')
    for n in graph["nodes"]:
        out.append(f'    <node id="{esc(n["id"])}">')
        for k in node_keys:
            v = n.get(k)
            if v:
                out.append(f'      <data key="{k}">{esc(v)}</data>')
        out.append("    </node>")
    for i, e in enumerate(graph["edges"]):
        out.append(f'    <edge id="e{i}" source="{esc(e["source"])}" '
                   f'target="{esc(e["target"])}"><data key="type">{esc(e["type"])}</data></edge>')
    out.append("  </graph>")
    out.append("</graphml>")
    return "\n".join(out) + "\n"


def _generate_graph_pages(nodes: dict) -> None:
    graph_dir = OUT_CONTENT / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    for f in graph_dir.glob("*.md"):
        f.unlink()

    (graph_dir / "_index.md").write_text(
        "+++\n"
        'title = "Content Graph"\n'
        'template = "v1-graph-index.json"\n'
        "\n"
        "[extra]\n"
        'lang = "en"\n'
        "+++\n",
        encoding="utf-8",
    )

    for nid, n in sorted(nodes.items()):
        section, slug = n["section"], n["slug"]
        page = (
            "+++\n"
            f"title = {_dumps('graph:' + nid)}\n"
            'template = "v1-graph-node.json"\n'
            f'path = "v1/graph/{section}/{slug}"\n'
            "\n"
            "[extra]\n"
            'lang = "en"\n'
            f'ego_path = "data/extracted/graph_nodes/{section}__{slug}.json"\n'
            "+++\n"
        )
        (graph_dir / f"node-{section}-{slug}.md").write_text(page, encoding="utf-8")


_SECTION_SPECS = (
    # (kind, src_subdir, page_template, sort_by, title)
    ("wiki", "wiki", "v1-wiki-page.json", "title", "Wiki"),
    ("timeline", "timeline", "v1-timeline-page.json", "title", "Timeline"),
    ("articles", "articles", "v1-article-page.json", "date", "Articles"),
    ("news", "news", "v1-news-page.json", "date", "News"),
)


def process_all_languages() -> None:
    """Run process_section across en + all EXTRA_LANGS for the content
    sections that have translations."""
    section_index_template = {
        "wiki": "v1-wiki-index.json",
        "timeline": "v1-timeline-index.json",
        "articles": "v1-articles-index.json",
        "news": "v1-news-index.json",
    }
    # Default English first.
    for kind, src_subdir, page_tpl, _sort, _title in _SECTION_SPECS:
        process_section(kind=kind, src_subdir=src_subdir, page_template=page_tpl)

    # Then each non-default language.
    for lang in EXTRA_LANGS:
        _ensure_lang_root_index(lang)
        for kind, src_subdir, page_tpl, sort_by, title in _SECTION_SPECS:
            n = process_section(kind=kind, src_subdir=src_subdir, page_template=page_tpl, lang=lang)
            if n:
                _ensure_lang_section_index(
                    lang,
                    kind,
                    title=title,
                    template=section_index_template[kind],
                    sort_by=sort_by,
                )


def main() -> int:
    print(f"Prebuild starting at {now_iso()}")
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_CONTENT.mkdir(parents=True, exist_ok=True)

    process_all_languages()
    process_traditions()
    process_sources()
    process_translations()
    process_library()
    for lang in EXTRA_LANGS:
        _ensure_lang_root_index(lang)
        process_library(lang=lang)
    process_glossary()
    build_graph()

    print("Prebuild complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
