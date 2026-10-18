# Wheel of Heaven API

Static JSON API for Wheel of Heaven library and content data.

## Overview

This is a Zola-powered static API that generates JSON endpoints from the library data. No server required - just static JSON files served via CDN.

## Endpoints

### Base URL
```
https://api.wheelofheaven.world
```

### Available Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | API info and available endpoints |
| `/v1/context` | Full project context for LLM/AI consumption |
| `/v1/context/terminology` | Key terms and definitions |
| `/v1/context/hypothesis` | Detailed hypothesis explanation |
| `/v1/context/timeline` | Precessional World Ages timeline |
| `/v1/catalog` | Full library catalog |
| `/v1/traditions` | List of religious/philosophical traditions |
| `/v1/books` | List of all books with links |
| `/v1/books/{slug}` | Full book with content |
| `/v1/books/{slug}/meta` | Book metadata only |
| `/v1/search` | Lightweight search index |

Book and book metadata responses include `data.version` when a
`data-library` record defines structured version/provenance metadata in its
`_meta.json`.

Library chapter responses resolve `kindByLang` for the requested language before
falling back to `kind`. Explicit edition gaps return an empty `text`, plus the
language's `alignment` record and original `sourceText`; they do not silently
substitute French for missing English. Shared passages carry the same metadata.

### Context Endpoints (for AI/LLM)

The `/v1/context` endpoints provide structured context optimized for AI systems:

- **`/v1/context`** - Project overview, core hypothesis, and navigation
- **`/v1/context/terminology`** - Comprehensive glossary of key terms
- **`/v1/context/hypothesis`** - Detailed explanation of the Wheel of Heaven hypothesis
- **`/v1/context/timeline`** - The 12 World Ages with dates and significance

### Response Format

All responses follow a consistent structure:

```json
{
  "apiVersion": "v1",
  "kind": "Book",
  "metadata": {
    "generated": "2025-01-24T12:00:00Z"
  },
  "data": { ... },
  "links": { ... }
}
```

### Content graph

`/v1/graph/` contains published English wiki, article, timeline, and news nodes.
`/v1/graph/{section}/{slug}/` provides each node's incoming/outgoing edges and neighbors.
Downloads are available at `/v1/graph/content-graph.json` and `/v1/graph/content-graph.graphml`.
Drafts are excluded from every graph surface.

Curated `see_also`/`canon_links` and in-body wiki shortcodes share canonical slug and declared alias resolution.
Links to the same canonical node are deduplicated per edge type; self-links are omitted.
Language prefixes project onto the English graph, and query strings/fragments do not change page identity.
A filename is not treated as an alias unless the page declares it.

The QA report distinguishes unresolved local page targets (`qa.dangling`) from verified published destinations outside the graph (`qa.outside_graph`), such as library landing pages.
Verification uses the English `data/content` routes, including explicit paths and aliases; missing library paths remain dangling.
Off-site URLs appear separately in `qa.external`; their availability is not checked.
Links to drafts or non-rendered pages are counted in `stats.excluded_links` without publishing their identifiers.
The graph does not validate anchor existence or extract ordinary Markdown links.

Every prebuild replaces graph data/downloads, removes stale generated ego data and page stubs, and invalidates `public/v1/graph/` before Zola renders fresh endpoints.
Run the complete build before serving output after a prebuild.
For the verified baseline and alias inventory, see [the graph audit](docs/content-graph-audit.md).

## Development

### Prerequisites

- [mise](https://mise.jdx.dev/) for tooling
- Zola 0.21.0 (installed via mise)

### Commands

```bash
# Build the API
mise run build

# Start dev server (localhost:1198)
mise run serve

# Check for errors
mise run check

# Focused graph regression tests (standard library only)
mise exec -- python3 -m unittest discover -s scripts -p 'test_graph.py' -v
```

### Adding a New Book

1. Add the book data to `data/library/`
2. Create a content file in `content/v1/books/{slug}.md`:
   ```toml
   +++
   title = "Book Title"
   slug = "book-slug"
   template = "v1-book.json"
   +++
   ```
3. Rebuild: `mise run build`

## Data Sources

This API generates JSON from two data submodules:

| Submodule | Path | Description |
|-----------|------|-------------|
| [data-library](https://github.com/wheelofheaven/data-library) | `data/library/` | Book/scripture JSON data |
| [data-content](https://github.com/wheelofheaven/data-content) | `data/content/` | Wiki, timeline, resources (Markdown) |

To update:
```bash
git submodule update --remote
```

## Deployment

The `public/` directory contains the generated JSON files, ready for deployment to any static hosting (Cloudflare Pages, Netlify, Vercel, etc.).

## Documentation

For the architectural context (who consumes the API, how it's built, how it sits next to www and the shared data submodules), see [docs.wheelofheaven.world/architecture/sites/api](https://docs.wheelofheaven.world/architecture/sites/api/). For the build / deploy chain across all sites, see [CI & Deploy](https://docs.wheelofheaven.world/contributing/dev/ci-deploy/).

## License

CC0-1.0 (Public Domain)
