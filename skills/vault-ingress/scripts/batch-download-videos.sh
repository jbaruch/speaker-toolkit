#!/usr/bin/env bash
# Download multiple YouTube videos in parallel for slide extraction.
#
# Usage:
#   batch-download-videos.sh <vault_root> ID1 ID2 ID3 ...
#
# Downloads up to 3 videos concurrently at 720p into
# <vault_root>/slides-rebuild/<youtube_id>/<youtube_id>.mp4

set -euo pipefail

vault_root="$1"; shift

for yt_id in "$@"; do
  (
    mkdir -p "${vault_root}/slides-rebuild/${yt_id}"
    yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]" \
      --merge-output-format mp4 \
      -o "${vault_root}/slides-rebuild/${yt_id}/${yt_id}.mp4" \
      "https://www.youtube.com/watch?v=${yt_id}" 2>/dev/null
    echo "Downloaded: ${yt_id}"
  ) &
  # Limit concurrency to 3
  [ "$(jobs -r -p | wc -l)" -ge 3 ] && wait -n
done
wait
