#!/usr/bin/env python3
"""Package the Wheel of Heaven CC0 datasets for HuggingFace Datasets + Kaggle.

Assembles a self-contained upload folder per dataset per platform under
scripts/dist/{platform}/{slug}/ — the data files plus the platform's metadata
(a HuggingFace dataset card README.md, or a Kaggle dataset-metadata.json). This
step needs no accounts and no network; it's fully runnable offline. The final
`upload` is a one-liner per dataset that you run with your own token (see the
printed instructions).

Why HF + Kaggle (and not a DOI repo): both are high-authority backlinks with a
real audience, and Kaggle is itself a Google Dataset Search source — so we keep
the second Dataset-Search listing without a DOI or the de-ranking risk that
individual-account uploads hit on Zenodo.

Usage:
    python scripts/build_distribution.py --kaggle-user <handle>
    python scripts/build_distribution.py --only flood-myths --kaggle-user <handle>

Then, per the printed commands:
    huggingface-cli upload <hf-user>/<repo> scripts/dist/huggingface/<slug> --repo-type=dataset
    kaggle datasets create -p scripts/dist/kaggle/<slug>
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static" / "v1"
DIST = Path(__file__).resolve().parent / "dist"

WWW = "https://www.wheelofheaven.world"
API = "https://api.wheelofheaven.world"
AUTHOR = "Zara Zinsfuss"
ORG = "Wheel of Heaven"
VERSION = "2026.07"

# slug -> title, blurb, keywords, columns, files (relative to static/v1), landing, records
DATASETS = {
    "content-graph": {
        "title": "Wheel of Heaven Content Graph",
        "subtitle": "Typed knowledge graph of the Wheel of Heaven corpus (JSON + GraphML, CC0)",
        "blurb": "A typed knowledge graph of the Wheel of Heaven corpus: every page is a node, and "
                 "every curated *See also* link and in-text cross-reference is a directed, typed edge. "
                 "Ships with an orphan / asymmetric-link QA block. JSON and GraphML.",
        "keywords": ["knowledge-graph", "comparative-mythology", "ancient-astronaut-theory",
                     "network-dataset", "linked-data", "digital-humanities"],
        "columns": "nodes (id, section, slug, kind, title, url, claim_type, category, degree) + "
                   "edges (source, target, type: see_also | in_body)",
        "files": ["graph/content-graph.json", "graph/content-graph.graphml"],
        "landing": f"{WWW}/datasets/content-graph/",
        "records": "graph over the full corpus",
    },
    "flood-myths": {
        "title": "Wheel of Heaven Flood-Myth Concordance",
        "subtitle": "Eleven ancient flood traditions compared side by side (CC0)",
        "blurb": "A comparative table of eleven ancient flood traditions — survivor, decreeing power, "
                 "warner, cause, vessel, birds released, landing place, and aftermath — with links to "
                 "the digitized source texts.",
        "keywords": ["flood-myth", "deluge", "comparative-mythology", "ancient-near-east",
                     "atrahasis", "gilgamesh", "genesis", "digital-humanities"],
        "columns": "tradition, source_text, approx_date, survivor, flood_decreed_by, warned_by, "
                   "cause, vessel, birds_released, landing_place, aftermath, woh_library",
        "files": ["datasets/flood-myths.csv", "datasets/flood-myths.json"],
        "landing": f"{WWW}/datasets/flood-myths/",
        "records": "11 traditions",
    },
    "divine-council-index": {
        "title": "Wheel of Heaven Divine-Council Index",
        "subtitle": "The divine council across twelve ancient traditions (CC0)",
        "blurb": "Seventeen attestations of the divine council across twelve ancient traditions — presiding "
                 "figure, council term, members, function, and primary reference — with links to the "
                 "digitized texts.",
        "keywords": ["divine-council", "sons-of-god", "assembly-of-the-gods", "comparative-religion",
                     "ancient-near-east", "ugaritic", "biblical-studies", "digital-humanities"],
        "columns": "tradition, source_text, reference, council_term, presiding_figure, members, "
                   "function, woh_library",
        "files": ["datasets/divine-council-index.csv", "datasets/divine-council-index.json"],
        "landing": f"{WWW}/datasets/divine-council-index/",
        "records": "17 attestations across 12 traditions",
    },
    "theomachy-crossrefs": {
        "title": "Wheel of Heaven Theomachy Cross-References",
        "subtitle": "The combat myth (chaoskampf) across eight traditions (CC0)",
        "blurb": "The combat myth (*chaoskampf*) across eight traditions — champion, adversary, chaos "
                 "form, weapon, outcome, and reference — with links to the digitized texts.",
        "keywords": ["theomachy", "chaoskampf", "combat-myth", "comparative-mythology",
                     "ancient-near-east", "dragon-slaying", "leviathan", "digital-humanities"],
        "columns": "tradition, source_text, reference, champion, adversary, chaos_form, weapon, "
                   "outcome, woh_library",
        "files": ["datasets/theomachy-crossrefs.csv", "datasets/theomachy-crossrefs.json"],
        "landing": f"{WWW}/datasets/theomachy-crossrefs/",
        "records": "8 traditions",
    },
    "world-ages": {
        "title": "Wheel of Heaven Precessional World Ages",
        "subtitle": "The twelve precessional World Ages: zodiac, dates, mapping (CC0)",
        "blurb": "The twelve precessional World Ages on the corpus's reckoning — zodiac, symbol, "
                 "start/end year, Genesis-day mapping, and summary — extracted from the live timeline.",
        "keywords": ["precession-of-the-equinoxes", "great-year", "astrological-ages", "world-ages",
                     "archaeoastronomy", "age-of-aquarius", "chronology"],
        "columns": "age, zodiac, symbol, start_year, end_year, genesis_day, url, summary",
        "files": ["datasets/world-ages.csv", "datasets/world-ages.json"],
        "landing": f"{WWW}/datasets/world-ages/",
        "records": "12 ages",
    },
    "prophets-and-religions": {
        "title": "Wheel of Heaven Prophets & Religions Catalogue",
        "subtitle": "48 religious traditions, founders, and framework relevance (CC0)",
        "blurb": "Forty-eight religious traditions with founder/prophet, period, framework-relevant "
                 "content, and the corpus's authenticity assessment of the founding-contact claim "
                 "(offered transparently as an interpretive label, not a neutral rating).",
        "keywords": ["comparative-religion", "new-religious-movements", "prophets", "founders",
                     "revelation", "religious-studies", "digital-humanities"],
        "columns": "tradition, period, founder, authenticity, principal_content, woh_wiki",
        "files": ["datasets/prophets-and-religions.csv", "datasets/prophets-and-religions.json"],
        "landing": f"{WWW}/datasets/prophets-and-religions/",
        "records": "48 traditions",
    },
}


def hf_card(slug, d):
    """HuggingFace dataset card: YAML frontmatter + markdown body."""
    tags = "".join(f"\n- {k}" for k in d["keywords"])
    fmt = "json" if slug == "content-graph" else "csv"
    front = (
        "---\n"
        "license: cc0-1.0\n"
        f"pretty_name: {d['title']}\n"
        "language:\n- en\n"
        "tags:" + tags + "\n"
        "---\n\n"
    )
    body = (
        f"# {d['title']}\n\n"
        f"{d['blurb']}\n\n"
        f"- **Records:** {d['records']}\n"
        f"- **Columns / structure:** {d['columns']}\n"
        f"- **Formats:** {', '.join(Path(f).suffix[1:].upper() for f in d['files'])}\n"
        f"- **License:** CC0-1.0 (public domain)\n"
        f"- **Version:** {VERSION}\n\n"
        "## Provenance\n\n"
        f"Extracted from the live [Wheel of Heaven]({WWW}) corpus and published as open data. "
        f"A documented landing page with a citation widget lives at "
        f"[{d['landing']}]({d['landing']}); the same files are served from the project API at "
        f"[{API}/v1/]({API}/v1/).\n\n"
        "## Citation\n\n"
        "```\n"
        f"{AUTHOR}. {d['title']}. {ORG}, 2026. CC0-1.0. {d['landing']}\n"
        "```\n"
    )
    return front + body


def kaggle_meta(slug, d, kaggle_user):
    # Kaggle requires the subtitle to be 20–80 characters.
    subtitle = d["subtitle"]
    if not (20 <= len(subtitle) <= 80):
        sys.exit(f"{slug}: subtitle must be 20–80 chars, got {len(subtitle)}: {subtitle!r}")
    desc = (
        f"{d['blurb'].replace('*', '')}\n\n"
        f"Records: {d['records']}. Columns: {d['columns']}. License: CC0-1.0 (public domain).\n\n"
        f"Extracted from the Wheel of Heaven corpus. Documented landing page with a citation widget: "
        f"{d['landing']} — API copy: {API}/v1/.\n"
    )
    return {
        "title": d["title"],
        "id": f"{kaggle_user}/{slug}",
        "subtitle": subtitle,
        "description": desc,
        "licenses": [{"name": "CC0-1.0"}],
        "keywords": d["keywords"],
        "resources": [{"path": Path(f).name, "description": d["title"]} for f in d["files"]],
    }


def build(slug, d, kaggle_user):
    hf_dir = DIST / "huggingface" / slug
    kg_dir = DIST / "kaggle" / slug
    for folder in (hf_dir, kg_dir):
        folder.mkdir(parents=True, exist_ok=True)
        for rel in d["files"]:
            shutil.copy2(STATIC / rel, folder / Path(rel).name)
    (hf_dir / "README.md").write_text(hf_card(slug, d), encoding="utf-8")
    (kg_dir / "dataset-metadata.json").write_text(
        json.dumps(kaggle_meta(slug, d, kaggle_user), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    n = len(d["files"])
    print(f"  ✓ {slug}: hf card + kaggle meta + {n} file(s) → dist/{{huggingface,kaggle}}/{slug}/")


def main():
    ap = argparse.ArgumentParser(description="Package datasets for HuggingFace + Kaggle.")
    ap.add_argument("--kaggle-user", default="KAGGLE_USER",
                    help="your Kaggle handle (fills the dataset id); default is a placeholder")
    ap.add_argument("--only", metavar="SLUG", help="package a single dataset")
    args = ap.parse_args()

    slugs = [args.only] if args.only else list(DATASETS)
    for s in slugs:
        if s not in DATASETS:
            sys.exit(f"unknown dataset: {s} (known: {', '.join(DATASETS)})")
    missing = [str(STATIC / f) for s in slugs for f in DATASETS[s]["files"] if not (STATIC / f).exists()]
    if missing:
        sys.exit("missing source files:\n  " + "\n  ".join(missing))

    if DIST.exists():
        shutil.rmtree(DIST)
    print(f"Packaging {len(slugs)} dataset(s) → {DIST.relative_to(ROOT)}/  (kaggle user: {args.kaggle_user})\n")
    for s in slugs:
        build(s, DATASETS[s], args.kaggle_user)

    print("\nUpload commands (run with your own tokens — see setup notes):")
    print("  # HuggingFace (needs `pip install huggingface_hub` + `huggingface-cli login`):")
    for s in slugs:
        print(f"  huggingface-cli upload <hf-user>/{s} scripts/dist/huggingface/{s} --repo-type=dataset")
    print("  # Kaggle (needs `pip install kaggle` + ~/.kaggle/kaggle.json):")
    for s in slugs:
        print(f"  kaggle datasets create -p scripts/dist/kaggle/{s}")


if __name__ == "__main__":
    main()
