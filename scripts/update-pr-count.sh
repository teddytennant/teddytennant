#!/usr/bin/env bash
# Refresh the merged-upstream-PR count in README.md.
set -euo pipefail

query='is:pr author:teddytennant is:merged -user:teddytennant'
count=$(gh api -X GET search/issues -f q="$query" -f per_page=1 --jq '.total_count')

if ! [[ "$count" =~ ^[0-9]+$ ]] || [ "$count" -eq 0 ]; then
  echo "refusing to write a bad count: '$count'" >&2
  exit 1
fi

perl -0pi -e "s{(<!--pr-count-->)\\d+(<!--/pr-count-->)}{\${1}$count\${2}}" README.md
echo "count: $count"
