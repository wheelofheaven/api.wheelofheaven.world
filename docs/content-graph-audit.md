# Content graph audit — 2026-10-18

Reproduced with API base `1ae0f3c`, content `20dae0c3c6398b4bcff3dfaa0875e63da100fa2d`, library `5d43f3d80a0888b70a2cecdf9b7d9e9687f2379e`, and bibliography `5408267654e06f9e29fdba984fccc1ae59838f7c`.
Inputs were local committed snapshots in an isolated worktree; no consumer submodule pointers were changed.

| Metric | Before | After |
|---|---:|---:|
| Nodes | 201 | 195 |
| Wiki / articles / timeline / news | 148 / 28 / 16 / 9 | 148 / 22 / 16 / 9 |
| Edges | 1,942 | 1,887 |
| Curated edges | 1,084 | 1,087 |
| In-body edges | 858 | 800 |
| Reported dangling links | 13 | 0 |
| Verified links outside the graph | Included in dangling | 6 |
| Orphans | 3 | 3 |
| Asymmetric curated pairs | 752 | 753 |

## Draft exclusion

The previous graph included six articles with top-level `draft = true`:

- `as-foolish-to-search-for-the-beginning`
- `made-from-the-ground-to-bear-the-labor`
- `the-filing-cabinet-of-the-gods`
- `the-forty-chairs`
- `the-jubilee-and-the-machine`
- `the-reporter-at-the-razors-edge`

These accounted for 60 edges, all in-body.
Resolving existing aliases adds five distinct edges after duplicate/self-link suppression, yielding 1,887 edges.
Draft exclusion applies to all four graph sections, both edge directions, ego endpoints, and both downloads.
Repeated builds also clear stale generated pages, ego data, and rendered graph output.

## The 13 original warnings

Six link occurrences point to five existing published English library landing pages:

| Source | Destination |
|---|---|
| `news/library-first-audio-plays` | `/library/extraterrestrials-took-me-to-their-planet/` |
| `news/library-first-audio-plays` | `/library/the-book-which-tells-the-truth/` |
| `news/synthetic-cell-eats-and-divides` | `/library/the-book-which-tells-the-truth/` |
| `wiki/book-of-enoch` | `/library/book-of-enoch/` |
| `wiki/great-flood` | `/library/atrahasis-woh/` |
| `wiki/great-flood` | `/library/gilgamesh-woh/` |

All seven remaining occurrences use explicitly declared aliases:

| Alias | Canonical target | Original warning occurrences |
|---|---|---:|
| `/wiki/council-of-eternals/` | `/wiki/council-of-the-eternals/` | 4 |
| `/wiki/planet-of-the-eternals/` | `/wiki/elohim-home-planet/` | 1 |
| `/wiki/sons-of-elohim/` | `/wiki/nephilim/` | 1 |
| `/wiki/tree-of-knowledge/` | `/wiki/tree-of-the-knowledge-of-good-and-evil/` | 1 |

The Council alias occurs in `articles/sendy-and-the-raelian-messages` once and `wiki/genesis-toolbox` three times (one curated and two in-body).
The other aliases occur in `wiki/cyberparadism`, `wiki/great-flood`, and `wiki/tree-of-life`, respectively.
No content-link corrections or editorial decisions are needed for these warnings.

The remaining orphan nodes are `timeline/chronology`, `wiki/adamite-struggle`, and `wiki/elohimian-space-wars`.
Orphans and asymmetric curated links are informational editorial signals, not missing destinations; adding relationships remains outside this repair.

## Validation

- `mise exec -- python3 -m unittest discover -s scripts -p 'test_graph.py' -v`: seven passing regressions covering draft exclusion, aliases, destination classification, edge deduplication, conflicting routes, and stale output cleanup.
- `mise run build`: full prebuild, Zola render, and postbuild pass (12,221 pages and 1,082 sections).
- Rendered-output inspection: all 195 ego endpoints match their nodes, all corresponding content endpoints exist, and served JSON/GraphML downloads match the generated exports.
- Rebuild with stale draft page stubs, ego JSON, rendered `index.html`/`index.json` endpoints, and old exports deliberately restored: no draft artifacts survive.
- `git diff --check`: passes.
