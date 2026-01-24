#!/bin/bash
# Post-build script to rename HTML files to JSON

set -e

cd "$(dirname "$0")/.."

echo "Converting HTML to JSON..."

# Rename all index.html to index.json (keeps directory structure)
find public -name "index.html" -exec sh -c 'mv "$1" "${1%.html}.json"' _ {} \;

# Create _headers file for proper Content-Type
cat > public/_headers << 'EOF'
/*
  Content-Type: application/json
  Access-Control-Allow-Origin: *

/index.json
  Content-Type: application/json
EOF

echo "Done. Output structure:"
find public -type f -name "*.json" | sort
