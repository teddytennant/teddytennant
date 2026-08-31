#!/usr/bin/env bash
# Refresh the upstream section of README.md: the merged-PR count and the
# five most recently merged pull requests.
set -euo pipefail

query='is:pr author:teddytennant is:merged -user:teddytennant'

count=$(gh api -X GET search/issues -f q="$query" -f per_page=1 --jq '.total_count')

if ! [[ "$count" =~ ^[0-9]+$ ]] || [ "$count" -eq 0 ]; then
  echo "refusing to write a bad count: '$count'" >&2
  exit 1
fi

# The count is anchored on the sentence, not an HTML comment: a line starting
# with <!-- is an HTML block, and markdown links on it never render.
if ! grep -qE '^[0-9]+ \[merged pull requests\]' README.md; then
  echo "count anchor missing from README.md" >&2
  exit 1
fi

# Search cannot sort by merge date, so pull a recent window and sort it here.
recent=$(gh api -X GET search/issues \
  -f q="$query" -f sort=updated -f order=desc -f per_page=50 \
  --jq '[.items[] | select(.pull_request.merged_at)]
        | sort_by(.pull_request.merged_at) | reverse | .[:5] | .[]
        | [.pull_request.merged_at[0:10],
           (.repository_url | split("/") | last),
           .number, .html_url, .title] | @tsv')

if [ "$(printf '%s\n' "$recent" | grep -c .)" -ne 5 ]; then
  echo "refusing to write a short PR list" >&2
  exit 1
fi

block=""
while IFS=$'\t' read -r date repo number url title; do
  # Titles are arbitrary text from upstream; keep markdown from eating them.
  title=$(printf '%s' "$title" | perl -pe 's{([\\`*_\[\]<>])}{\\$1}g')
  block+="- $date · [$repo #$number]($url) — $title"$'\n'
done <<< "$recent"

COUNT="$count" BLOCK="$block" perl -0pi -e '
  s{^\d+(?= \[merged pull requests\])}{$ENV{COUNT}}m;
  s{(<!--recent-prs-->\n).*?(<!--/recent-prs-->)}{$1$ENV{BLOCK}$2}s;
' README.md

echo "count: $count"
printf '%s' "$block"
