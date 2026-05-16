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

## License

CC0-1.0 (Public Domain)
