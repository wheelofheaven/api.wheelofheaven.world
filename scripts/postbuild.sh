#!/bin/bash
# Post-build for api.wheelofheaven.world.
#
# Cloudflare Pages serves directory indexes from index.html by default.
# Our index.html files contain JSON (rendered from Tera .json templates),
# so we keep the filename and set Content-Type via _headers — this way
# https://api.wheelofheaven.world/v1/wiki/ resolves to the JSON natively.
#
# We also emit /v1/{path}/index.json copies for consumers that prefer
# the explicit-extension form (backwards-compatible with the original
# GitHub Pages setup) and write _redirects + _headers files.

set -e

cd "$(dirname "$0")/.."

echo "Postbuild: preparing public/ for Cloudflare Pages..."

# Note: explicit-extension URLs like /v1/wiki/elohim/index.json are handled
# by the /v1/*/index.json -> /v1/:splat/ 200 rewrite in _redirects below.
# We no longer mirror the JSON content as a sibling file because that
# doubles file count and bumps us against Cloudflare Pages' 20,000-file
# deployment cap.

# Top-level _headers: every served path returns application/json.
#
# THIS is the _headers that ships. It is written here, after `zola build`,
# so it overwrites anything static/ copied into public/ — which is why
# static/_headers was deleted: editing it looked like it worked and
# changed nothing. Add response headers here, not there.
#
# The Link header is the RFC 9727 catalog advertisement. This host is the
# likeliest place an agent enters the project — it is the API — and www
# alone used to send it, so an agent that landed on /v1/ had no path to
# the catalog, the auth policy or the MCP server. The URL is absolute,
# unlike www's copy: the catalog document is centralised on www so there
# is one copy that cannot drift, and a relative `/.well-known/api-catalog`
# here would resolve against this host, where it 404s. The catalog sends
# `Access-Control-Allow-Origin: *`, so cross-origin agents can follow it.
cat > public/_headers << 'EOF'
/*
  Content-Type: application/json; charset=utf-8
  Access-Control-Allow-Origin: *
  Access-Control-Allow-Methods: GET, HEAD, OPTIONS
  Link: <https://www.wheelofheaven.world/.well-known/api-catalog>; rel="api-catalog"
  X-License: CC0-1.0
  X-Citable: true
  X-API-Version: v1

# Long cache for stable meta surface
/v1/schema/*
  Cache-Control: public, max-age=86400, must-revalidate

/v1/enums/*
  Cache-Control: public, max-age=86400, must-revalidate

/v1/context/*
  Cache-Control: public, max-age=86400, must-revalidate

# Short cache for content
/v1/*
  Cache-Control: public, max-age=3600, must-revalidate

# Robots and sitemap as their native types
/robots.txt
  Content-Type: text/plain; charset=utf-8

/sitemap.xml
  Content-Type: application/xml; charset=utf-8

/llms.txt
  Content-Type: text/plain; charset=utf-8
EOF

# _redirects: keep historical .json-extension URLs working, alias bare paths to dirs.
cat > public/_redirects << 'EOF'
# Map old explicit-extension URLs to the new clean ones.
# (Both keep working; the directory form is canonical.)
/v1/*/index.json /v1/:splat/ 200

# Library URL canonicalisation. Bare /v1/books/ and /v1/traditions/ stay live
# as alias *listings*, but per-item paths under them route to the
# library-prefixed canonical pages. Per Decision 14, /v1/ URL permanence is
# preserved via 301 to the canonical URL.
/v1/books/:slug/meta /v1/library/books/:slug/meta 301
/v1/books/:slug/chapters /v1/library/books/:slug/chapters/ 301
/v1/books/:slug/chapters/:n /v1/library/books/:slug/chapters/:n 301
/v1/books/:slug/ /v1/library/books/:slug/ 301
/v1/books/:slug /v1/library/books/:slug/ 301
/v1/traditions/:slug/ /v1/library/traditions/:slug/ 301
/v1/traditions/:slug /v1/library/traditions/:slug/ 301

# Trailing-slash normalisation (CF Pages also does this by default; keep explicit).
EOF

echo "Done. Output summary:"
find public -type f -name "index.json" | wc -l | xargs -I {} echo "  index.json files: {}"
find public -type f -name "index.html" | wc -l | xargs -I {} echo "  index.html files: {}"
