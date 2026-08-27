#!/usr/bin/env bash
# Download YouTube videos in parallel for slide extraction, reporting each outcome.
#
# Usage:
#   batch-download-videos.sh <vault_root> ID1 ID2 ID3 ...
#
# Downloads up to 3 videos concurrently at 720p into
# <vault_root>/slides-rebuild/<youtube_id>/<youtube_id>.mp4
#
# Stdout: one tab-separated outcome line per id, in the order the ids were given.
#   OK    <id>  <bytes>            downloaded this run
#   SKIP  <id>  present <bytes>    already on disk and non-empty
#   FAIL  <id>  <reason>           nothing usable on disk; full log path in the reason
# Stderr: the resolved yt-dlp path and version, then one warning line per FAIL.
# Exit 0 when every id ended OK or SKIP, 1 when any id FAILed, 2 on a usage or
# yt-dlp resolution error.
#
# yt-dlp resolution order (first executable match wins), because a stale PATH
# binary 403s on every download while the pinned one succeeds (#371):
#   1. $YT_DLP                      explicit caller override
#   2. $VIRTUAL_ENV/bin/yt-dlp      the active virtualenv's pinned console script
#   3. <toolkit_root>/.venv/bin/yt-dlp
#   4. yt-dlp from PATH
#
# `-e` is dropped under the aggregate-reporting carve-out in
# rules/error-handling.md: each id is independent, every exit code is captured
# explicitly, and the script exits non-zero when any id failed.
set -uo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: batch-download-videos.sh <vault_root> ID1 [ID2 ...]" >&2
  exit 2
fi

vault_root="$1"; shift

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
toolkit_root="$(cd -- "${script_dir}/../../.." && pwd)"

resolve_ytdlp() {
  if [ -n "${YT_DLP:-}" ]; then
    if [ -x "${YT_DLP}" ]; then
      printf '%s\n' "${YT_DLP}"
      return 0
    fi
    echo "YT_DLP is set to '${YT_DLP}', which is not executable — point it at a yt-dlp binary or unset it" >&2
    return 1
  fi
  local candidate
  for candidate in "${VIRTUAL_ENV:-}/bin/yt-dlp" "${toolkit_root}/.venv/bin/yt-dlp"; do
    if [ -x "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  if candidate="$(command -v yt-dlp)"; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  echo "cannot find yt-dlp — install the pinned version with \`pip install -e .\` in the toolkit venv, or set YT_DLP to its path" >&2
  return 1
}

if ! ytdlp="$(resolve_ytdlp)"; then
  exit 2
fi
ytdlp_version="$("${ytdlp}" --version 2>/dev/null)"
if [ -z "${ytdlp_version}" ]; then
  echo "'${ytdlp}' did not report a version — reinstall yt-dlp or set YT_DLP to a working binary" >&2
  exit 2
fi
echo "yt-dlp: ${ytdlp} (${ytdlp_version})" >&2

work_dir="$(mktemp -d)"
# Invoked indirectly by the EXIT trap below.
# shellcheck disable=SC2329
cleanup() {
  rm -rf "${work_dir}"
  return 0
}
trap cleanup EXIT

file_size() {
  wc -c <"$1" | tr -d ' '
}

download_one() {
  local yt_id="$1"
  local outcome_file="${work_dir}/${yt_id}.outcome"
  local target_dir="${vault_root}/slides-rebuild/${yt_id}"
  local target="${target_dir}/${yt_id}.mp4"
  local log="${target_dir}/${yt_id}.yt-dlp.log"

  if [ -s "${target}" ]; then
    printf 'SKIP\t%s\tpresent %s\n' "${yt_id}" "$(file_size "${target}")" >"${outcome_file}"
    return 0
  fi

  if ! mkdir -p "${target_dir}"; then
    printf 'FAIL\t%s\tcannot create %s\n' "${yt_id}" "${target_dir}" >"${outcome_file}"
    return 0
  fi

  "${ytdlp}" -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]" \
    --merge-output-format mp4 \
    --no-progress \
    -o "${target}" \
    "https://www.youtube.com/watch?v=${yt_id}" >"${log}" 2>&1
  local rc=$?

  # yt-dlp can exit zero having produced nothing usable after a failed merge, so
  # the file is the verdict and the exit code only sharpens the reason.
  if [ -s "${target}" ]; then
    printf 'OK\t%s\t%s\n' "${yt_id}" "$(file_size "${target}")" >"${outcome_file}"
    return 0
  fi

  local detail
  detail="$(grep -a -m1 '^ERROR' "${log}" | tr -d '\n')"
  if [ -z "${detail}" ]; then
    detail="$(tail -n1 "${log}" | tr -d '\n')"
  fi
  if [ -z "${detail}" ]; then
    detail="no output file and no yt-dlp diagnostic"
  fi
  printf 'FAIL\t%s\trc=%s %s (log: %s)\n' "${yt_id}" "${rc}" "${detail}" "${log}" >"${outcome_file}"
  return 0
}

for yt_id in "$@"; do
  download_one "${yt_id}" &
  if [ "$(jobs -r -p | wc -l)" -ge 3 ]; then
    wait -n
  fi
done
wait

failed=0
for yt_id in "$@"; do
  outcome_file="${work_dir}/${yt_id}.outcome"
  if [ ! -f "${outcome_file}" ]; then
    printf 'FAIL\t%s\tworker produced no outcome\n' "${yt_id}"
    echo "warning: ${yt_id} — worker produced no outcome" >&2
    failed=1
    continue
  fi
  outcome="$(cat "${outcome_file}")"
  printf '%s\n' "${outcome}"
  case "${outcome}" in
    FAIL*)
      echo "warning: ${outcome}" >&2
      failed=1
      ;;
  esac
done

exit "${failed}"
