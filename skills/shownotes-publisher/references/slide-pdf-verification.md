# Verify the Slide PDF in Google Drive

Use this check when adding or replacing slides on the Jekyll shownotes site.
The approved local export is the reference. Resolve the specific PDF's file ID
in the talk's existing Drive folder. When replacing slides, update the file
already linked on the page. Reuse its ID.

After export and upload, read fresh Drive v3 `files.get` metadata for that ID
through the connected Drive tool or another authorized Drive client. Request
`id,mimeType,trashed,sha256Checksum,md5Checksum`. Save the returned File object
as temporary JSON. Drive exposes checksums for binary files such as PDFs.
[Google Drive File resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)

Run the verifier before writing the Slides field and again after any later
export or upload intended to replace that PDF.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/shownotes-publisher/scripts/verify-drive-slides.py" \
  "{exported_pdf}" "{drive_file_id}" < "{drive_metadata_json}"
```

Exit 0 emits JSON with `file_id`, `preview_url`, and `checksum_algorithm`.
The preview URL identifies matching bytes at the time of the metadata read.
Verify the preview opens as a signed-out reader before using the URL.
Authenticated metadata alone does not establish public access.

Exit 1 prints the verification failure to stderr and emits no URL. If the
checksum differs, let the existing upload finish or update the same Drive
file, then read fresh metadata and retry. A rendering iframe can still show
the previous revision. If verification or anonymous access fails, report slides
publication as incomplete. Omit the Slides field on a new page. On a slide
update, hold the replacement until it can be verified and preserve the
published page. Keep site-hosted PDFs out of this workflow.
