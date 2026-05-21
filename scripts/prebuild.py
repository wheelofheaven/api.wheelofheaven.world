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
OUT_DATA = ROOT / "data" / "extracted"
OUT_CONTENT = ROOT / "content" / "v1"

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


def process_section(
    *,
    kind: str,
    src_subdir: str,
    page_template: str,
) -> int:
    """Process one content section.

    Reads data/content/{src_subdir}/*.md, emits one Zola page per
    entry and a section index file at data/extracted/{kind}.json.
    """
    src = SRC_CONTENT / src_subdir
    if not src.exists():
        print(f"  {kind}: source dir missing ({src}); skipping")
        return 0

    dest_pages = OUT_CONTENT / kind
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
        page_path = dest_pages / f"{slug}.md"
        page_path.write_text(
            patch_frontmatter(raw, fm, new_template=page_template),
            encoding="utf-8",
        )

        # Index entry: minimal hot fields plus selected `[extra]` lifts.
        index_entry: dict = {
            "slug": slug,
            "title": fm.get("title", ""),
            "description": fm.get("description", ""),
            "url": f"/v1/{kind}/{slug}/",
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

    write_json(
        OUT_DATA / f"{kind}.json",
        {
            "version": "1.0",
            "generated": now_iso(),
            "count": len(entries),
            "entries": entries,
        },
    )
    print(f"  {kind}: {len(entries)} entries -> {dest_pages.relative_to(ROOT)}/")
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
    """Scan data/library/* for -woh translations and index their _meta.json."""
    if not SRC_LIBRARY.exists():
        print("  translations: library missing; skipping")
        return 0
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
        entries.append(
            {
                "slug": slug,
                "title": (meta.get("titles") or {}).get("en") or slug,
                "code": meta.get("code", ""),
                "originalLang": meta.get("originalLang", ""),
                "primaryLang": meta.get("primaryLang", "en"),
                "chapterCount": meta.get("chapterCount", 0),
                "url": f"/v1/translations/{slug}/",
                "library_url": f"/v1/library/books/{slug}/",
            }
        )
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
    print(f"  translations: {len(entries)} entries")
    return len(entries)


def process_glossary() -> int:
    """Copy data/content/i18n/glossary.json into data/extracted/."""
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
    terms = raw.get("terms") or raw.get("entries") or []
    print(f"  glossary: {len(terms) if isinstance(terms, list) else 'inline'} terms")
    return 1


def main() -> int:
    print(f"Prebuild starting at {now_iso()}")
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_CONTENT.mkdir(parents=True, exist_ok=True)

    process_section(kind="wiki", src_subdir="wiki", page_template="v1-wiki-page.json")
    process_section(kind="timeline", src_subdir="timeline", page_template="v1-timeline-page.json")
    process_section(kind="articles", src_subdir="articles", page_template="v1-article-page.json")
    process_section(kind="news", src_subdir="news", page_template="v1-news-page.json")
    process_traditions()
    process_translations()
    process_glossary()

    print("Prebuild complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
