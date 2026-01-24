#!/usr/bin/env python3
"""
Pre-build script to extract wiki and timeline data from markdown files.
Generates JSON data files that Zola can load via load_data().
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

# Paths
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = ROOT_DIR / "data" / "content"
OUTPUT_DIR = ROOT_DIR / "data" / "extracted"


def parse_toml_frontmatter(content: str) -> tuple[dict, str]:
    """Extract TOML frontmatter and body from markdown file."""
    if not content.startswith("+++"):
        return {}, content

    parts = content.split("+++", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_str = parts[1].strip()
    body = parts[2].strip()

    # Simple TOML parser for frontmatter
    frontmatter = {}
    current_section = frontmatter

    for line in frontmatter_str.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Section header like [extra]
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1]
            if section_name not in frontmatter:
                frontmatter[section_name] = {}
            current_section = frontmatter[section_name]
            continue

        # Key = value
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Parse value
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            elif value.startswith("["):
                # Simple array parsing
                try:
                    value = json.loads(value.replace("'", '"'))
                except:
                    pass
            elif value == "true":
                value = True
            elif value == "false":
                value = False
            elif value.isdigit():
                value = int(value)

            current_section[key] = value

    return frontmatter, body


def extract_summary(body: str, max_length: int = 500) -> str:
    """Extract a plain text summary from markdown body."""
    # Remove markdown formatting
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', body)  # Links
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)  # Images
    text = re.sub(r'#{1,6}\s+', '', text)  # Headers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Italic
    text = re.sub(r'`[^`]+`', '', text)  # Inline code
    text = re.sub(r'```[\s\S]*?```', '', text)  # Code blocks
    text = re.sub(r'>\s+[^\n]+', '', text)  # Blockquotes
    text = re.sub(r'\n{2,}', '\n', text)  # Multiple newlines
    text = text.strip()

    # Get first paragraph
    paragraphs = text.split('\n\n')
    for p in paragraphs:
        p = p.strip()
        if len(p) > 50:  # Skip very short paragraphs
            if len(p) > max_length:
                return p[:max_length].rsplit(' ', 1)[0] + '...'
            return p

    return text[:max_length] if text else ""


def process_wiki():
    """Process all wiki entries."""
    wiki_dir = CONTENT_DIR / "wiki"
    if not wiki_dir.exists():
        print(f"Wiki directory not found: {wiki_dir}")
        return []

    entries = []

    for md_file in sorted(wiki_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue

        content = md_file.read_text(encoding="utf-8")
        frontmatter, body = parse_toml_frontmatter(content)

        if not frontmatter.get("title"):
            continue

        entry = {
            "slug": frontmatter.get("slug", md_file.stem),
            "title": frontmatter.get("title", ""),
            "description": frontmatter.get("description", ""),
            "summary": extract_summary(body),
            "template": frontmatter.get("template", ""),
            "aliases": frontmatter.get("aliases", []),
        }

        # Add extra fields if present
        extra = frontmatter.get("extra", {})
        if extra:
            entry["extra"] = extra

        entries.append(entry)

    return entries


def process_timeline():
    """Process all timeline entries."""
    timeline_dir = CONTENT_DIR / "timeline"
    if not timeline_dir.exists():
        print(f"Timeline directory not found: {timeline_dir}")
        return []

    entries = []

    for md_file in sorted(timeline_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue

        content = md_file.read_text(encoding="utf-8")
        frontmatter, body = parse_toml_frontmatter(content)

        if not frontmatter.get("title"):
            continue

        entry = {
            "slug": frontmatter.get("slug", md_file.stem),
            "title": frontmatter.get("title", ""),
            "description": frontmatter.get("description", ""),
            "summary": extract_summary(body),
            "weight": frontmatter.get("weight", 0),
        }

        # Add extra fields if present
        extra = frontmatter.get("extra", {})
        if extra:
            entry["extra"] = extra

        entries.append(entry)

    # Sort by weight
    entries.sort(key=lambda x: x.get("weight", 0))

    return entries


def main():
    print("Extracting wiki and timeline data...")

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Process wiki
    wiki_entries = process_wiki()
    wiki_data = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(wiki_entries),
        "entries": wiki_entries
    }

    wiki_output = OUTPUT_DIR / "wiki.json"
    wiki_output.write_text(json.dumps(wiki_data, indent=2, ensure_ascii=False))
    print(f"  Wiki: {len(wiki_entries)} entries -> {wiki_output}")

    # Process timeline
    timeline_entries = process_timeline()
    timeline_data = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(timeline_entries),
        "entries": timeline_entries
    }

    timeline_output = OUTPUT_DIR / "timeline.json"
    timeline_output.write_text(json.dumps(timeline_data, indent=2, ensure_ascii=False))
    print(f"  Timeline: {len(timeline_entries)} entries -> {timeline_output}")

    print("Done!")


if __name__ == "__main__":
    main()
