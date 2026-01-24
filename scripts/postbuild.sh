#!/bin/bash
# Post-build script to rename HTML files to JSON

set -e

cd "$(dirname "$0")/.."

echo "Converting HTML to JSON..."

# Rename index.html to index.json throughout
find public -name "index.html" | while read file; do
    dir=$(dirname "$file")
    # Get the parent directory name for the new filename
    parent=$(basename "$dir")
    grandparent=$(dirname "$dir")

    if [ "$parent" = "public" ]; then
        # Root index stays as is but rename to .json
        mv "$file" "$dir/index.json"
    else
        # Move index.html up one level with directory name + .json
        mv "$file" "$grandparent/$parent.json"
        rmdir "$dir" 2>/dev/null || true
    fi
done

# Clean up empty directories
find public -type d -empty -delete 2>/dev/null || true

echo "Done. Output structure:"
find public -type f -name "*.json" | sort
