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

# Mirror every generated index.html as index.json for explicit-extension consumers.
# (Keep the .html original so CF Pages' directory-index resolution still serves it.)
find public -name "index.html" -print0 | while IFS= read -r -d '' html_file; do
  cp "$html_file" "${html_file%.html}.json"
done

# Top-level _headers: every served path returns application/json.
cat > public/_headers << 'EOF'
/*
  Content-Type: application/json; charset=utf-8
  Access-Control-Allow-Origin: *
  Access-Control-Allow-Methods: GET, HEAD, OPTIONS
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

# Trailing-slash normalisation (CF Pages also does this by default; keep explicit).
EOF

echo "Done. Output summary:"
find public -type f -name "index.json" | wc -l | xargs -I {} echo "  index.json files: {}"
find public -type f -name "index.html" | wc -l | xargs -I {} echo "  index.html files: {}"
