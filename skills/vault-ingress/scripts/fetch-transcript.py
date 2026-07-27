#!/usr/bin/env python3
"""Fetch a talk transcript, validate it, and write it only if it is real.

This exists because the previous transcript fetch was an inline `python3 -c`
heredoc. When `youtube-transcript-api` 1.0 removed the `YouTubeTranscriptApi.
get_transcript` classmethod, every call raised, and the heredoc's traceback was
written to the transcript path. Its error handler then raised too (`NameError:
name 'sys' is not defined`), so the failure path failed as well.

Four vault "transcripts" are that traceback. Two more are zero bytes. Nothing
validated the output, so a talk with a stack trace for a transcript was
indistinguishable from a talk with a transcript, and one talk was marked
`processed` off an empty file.

The fix is not a better heredoc. Per `rules/script-delegation.md` Scripts Are
Real Files, a deterministic operation gets a real file with an exit code, a
stderr channel, and tests. The validation below is the part that matters, and it
is pure so CI can test every failure mode without a network.

Sources, in order:
  1. YouTube caption track (fast, no audio download)
  2. Local Whisper transcription of the downloaded audio (fallback, and the only
     option when a video has no caption track)

Usage:
    fetch-transcript.py <video-id-or-url> --out <path> [--languages en,ru,he]
                        [--method auto|captions|whisper] [--force]
                        [--duration-seconds N] [--min-words N]

Output: one JSON object on stdout —
    {"ok": bool, "video_id": "...", "method": "captions|whisper|none",
     "words": int, "path": "...", "reason": "..."}
Exit:   0 wrote a valid transcript (or --force absent and a valid one existed)
        1 could not obtain a valid transcript — nothing was written
        2 argument or tool-state error

The output path is written ATOMICALLY and only after validation passes, so a
failed fetch can never leave a corrupt file where a transcript belongs.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Text that proves the "transcript" is a crash report rather than speech. Anchored
# at the head of the file: a talk about Python may legitimately say "traceback".
FAILURE_SIGNATURES = (
    "Traceback (most recent call last)",
    "AttributeError:",
    "NameError:",
    "ModuleNotFoundError:",
    "ImportError:",
)
FAILURE_SCAN_CHARS = 400

# A caption track that is almost entirely these markers carries no speech.
NON_SPEECH_MARKERS = ("[Music]", "[Applause]", "[Laughter]", "[музыка]")

WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

DEFAULT_MIN_WORDS = 400
# Words per minute below which a transcript cannot plausibly cover the runtime.
# Conference delivery runs 110-160 wpm; 30 is a floor no real talk crosses, so
# this catches a caption track that returned only its first minute.
MIN_WORDS_PER_MINUTE = 30


def count_words(text):
    """Words, counting Cyrillic and accented Latin — not just [a-z]."""
    return len(WORD.findall(text))


def validate_transcript(text, *, min_words=DEFAULT_MIN_WORDS, duration_seconds=None):
    """Return (ok, reason). Pure — every failure mode is CI-testable.

    `reason` is actionable on failure per `rules/error-handling.md`: it names
    what was found, not merely that something was wrong.
    """
    if not text or not text.strip():
        return False, "transcript is empty"

    head = text[:FAILURE_SCAN_CHARS]
    for signature in FAILURE_SIGNATURES:
        if signature in head:
            return False, (
                f"transcript begins with a Python error ({signature.rstrip(':')}) — "
                "this is a captured crash, not speech; re-fetch it")

    words = count_words(text)
    if words < min_words:
        return False, (
            f"transcript has {words} words, below the {min_words}-word floor — "
            "too short to be a talk; the fetch probably returned a stub")

    marker_chars = sum(text.count(m) * len(m) for m in NON_SPEECH_MARKERS)
    if marker_chars > len(text) * 0.5:
        return False, (
            "transcript is mostly non-speech markers ([Music]/[Applause]) — "
            "the caption track carries no usable speech; transcribe the audio")

    if duration_seconds:
        minutes = duration_seconds / 60.0
        if minutes > 0 and words / minutes < MIN_WORDS_PER_MINUTE:
            return False, (
                f"transcript has {words} words for {minutes:.0f} minutes "
                f"({words / minutes:.0f} wpm), below the {MIN_WORDS_PER_MINUTE} "
                "wpm floor — it likely covers only part of the talk")

    return True, f"{words} words"


VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")


def resolve_video_id(value):
    """Accept a bare 11-character id or any YouTube URL carrying one."""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    match = VIDEO_ID.search(value)
    return match.group(1) if match else None


def segments_to_text(segments):
    """Flatten caption segments to text.

    Handles both shapes the library has used: dicts with a "text" key (<=0.6)
    and objects with a .text attribute (>=1.0). Pinning to one shape is what
    broke the previous fetch.
    """
    lines = []
    for segment in segments:
        text = segment.get("text") if isinstance(segment, dict) else getattr(segment, "text", None)
        if text:
            lines.append(text)
    return "\n".join(lines)


def fetch_captions(video_id, languages):
    """Return caption text, or None when no track is available.

    The 1.0 API is instance-based (`YouTubeTranscriptApi().fetch`); the older one
    was a classmethod (`.get_transcript`). Both are tried so the script survives
    the next rename instead of writing a traceback into the corpus.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api import YouTubeTranscriptApiException
    except ImportError:
        print("youtube-transcript-api is not installed — "
              "`pip install youtube-transcript-api`, or pass --method whisper",
              file=sys.stderr)
        return None

    api = YouTubeTranscriptApi()
    try:
        if hasattr(api, "fetch"):
            segments = api.fetch(video_id, languages=languages)
        elif hasattr(YouTubeTranscriptApi, "get_transcript"):
            segments = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
        else:
            print("youtube-transcript-api exposes neither .fetch nor .get_transcript; "
                  "the API changed again — update fetch_captions()", file=sys.stderr)
            return None
    except YouTubeTranscriptApiException as exc:
        # Every "this video has no usable caption track" case — subtitles
        # disabled, no track in the requested languages, age restriction, IP
        # block. All are normal and all must fall through to Whisper rather than
        # propagating: an uncaught library exception here is precisely how the
        # previous fetch ended up writing its own traceback into the corpus.
        print(f"caption track unavailable for {video_id}: "
              f"{type(exc).__name__}: {str(exc).splitlines()[0]}", file=sys.stderr)
        return None
    return segments_to_text(segments)


def fetch_whisper(video_id, work_dir, model):
    """Download audio and transcribe locally. Returns text, or None on failure."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    audio = Path(work_dir) / "audio.mp3"
    try:
        download = subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3", "--no-playlist",
             "-o", str(Path(work_dir) / "audio.%(ext)s"), url],
            capture_output=True, text=True,
        )
    except (FileNotFoundError, OSError) as exc:
        # A missing yt-dlp must not escape as a traceback: this script's callers
        # parse its stdout JSON, and a script that dies without emitting it is
        # the same silent-failure shape the whole file exists to prevent.
        print(f"cannot run yt-dlp ({exc}) — install it with "
              "`brew install yt-dlp` or `pip install yt-dlp`", file=sys.stderr)
        return None
    if download.returncode != 0 or not audio.exists():
        print(f"yt-dlp could not download audio for {video_id}: "
              f"{download.stderr.strip()[:400]}", file=sys.stderr)
        return None

    # The Python API, not a CLI. `python -m mlx_whisper` has no `__main__` and
    # the console-script name is not reliably on PATH for every caller, so
    # shelling out drifts; `transcribe()` returns the text directly.
    try:
        import mlx_whisper
    except ImportError:
        print("mlx-whisper is not installed (Apple Silicon only) — "
              "`pip install mlx-whisper`, or supply the transcript by hand. "
              "On other platforms use a caption track or an external "
              "transcription service.", file=sys.stderr)
        return None

    try:
        result = mlx_whisper.transcribe(str(audio), path_or_hf_repo=model)
    except (OSError, ValueError, RuntimeError) as exc:
        # Model download failure, unreadable audio, or an unsupported runtime.
        # Same contract reason as the yt-dlp guard above.
        print(f"mlx_whisper could not transcribe {video_id}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    text = result.get("text") if isinstance(result, dict) else None
    if not text:
        print(f"mlx_whisper returned no text for {video_id}", file=sys.stderr)
        return None
    return text


def write_atomically(path, text):
    """Write via a temp file in the same directory, then replace.

    A half-written transcript is the same defect class as a traceback-as-
    transcript: it looks like data.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".partial")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        # `finally`, not a catch: cleanup must also run on KeyboardInterrupt and
        # SystemExit, and neither may be swallowed (`rules/error-handling.md`).
        # After a successful os.replace the temp path is gone, so this is a no-op
        # on the happy path.
        if os.path.exists(tmp):
            os.unlink(tmp)


def emit(ok, video_id, method, words, path, reason, code):
    print(json.dumps({"ok": ok, "video_id": video_id, "method": method,
                      "words": words, "path": str(path), "reason": reason}))
    sys.exit(code)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("video", help="YouTube video id, or any URL containing one")
    parser.add_argument("--out", required=True, help="transcript output path")
    parser.add_argument("--languages", default="en,ru,he,fr,de",
                        help="comma-separated caption language preference")
    parser.add_argument("--method", default="auto",
                        choices=("auto", "captions", "whisper"))
    parser.add_argument("--force", action="store_true",
                        help="refetch even when a valid transcript already exists")
    parser.add_argument("--duration-seconds", type=int, default=None,
                        help="video runtime, enabling the words-per-minute check")
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    parser.add_argument("--whisper-model",
                        default="mlx-community/whisper-large-v3-turbo")
    args = parser.parse_args(argv)

    video_id = resolve_video_id(args.video)
    if not video_id:
        print(f"cannot find an 11-character video id in {args.video!r} — "
              "pass a bare id or a YouTube URL", file=sys.stderr)
        return 2

    out = Path(args.out)
    if out.exists() and not args.force:
        existing = out.read_text(encoding="utf-8", errors="replace")
        ok, reason = validate_transcript(
            existing, min_words=args.min_words,
            duration_seconds=args.duration_seconds)
        if ok:
            emit(True, video_id, "existing", count_words(existing), out,
                 f"kept existing transcript ({reason})", 0)
        print(f"existing transcript at {out} is not usable: {reason}", file=sys.stderr)

    languages = [lang.strip() for lang in (args.languages or "").split(",") if lang.strip()]
    attempts = [name for name in ("captions", "whisper")
                if args.method in ("auto", name)]

    failures = []
    for name in attempts:
        if name == "captions":
            text = fetch_captions(video_id, languages)
        else:
            with tempfile.TemporaryDirectory() as work_dir:
                text = fetch_whisper(video_id, work_dir, args.whisper_model)
        if text is None:
            failures.append(f"{name}: unavailable")
            continue
        ok, reason = validate_transcript(
            text, min_words=args.min_words, duration_seconds=args.duration_seconds)
        if ok:
            write_atomically(out, text)
            emit(True, video_id, name, count_words(text), out, reason, 0)
        failures.append(f"{name}: {reason}")

    emit(False, video_id, "none", 0, out,
         "no source produced a valid transcript — " + "; ".join(failures), 1)


if __name__ == "__main__":
    sys.exit(main())
