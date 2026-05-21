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

FRONTMATTER_RE = re.compile(r"^\+\+\+\s*\n(.*?)\n\+\+\+\s*\n?", re.DOTALL)

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
    if not raw.startswith("+++"):
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
    process_glossary()

    print("Prebuild complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
