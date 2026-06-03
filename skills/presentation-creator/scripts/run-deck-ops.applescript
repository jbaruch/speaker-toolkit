-- run-deck-ops.applescript
-- Thin driver: hands 5 string args to the RunDeckOps VBA macro inside the
-- real PowerPoint app. PowerPoint performs the edit and writes the file, so
-- the output .pptx is not corrupted and per-slide backgrounds survive.
--
-- Usage (normally invoked by run-deck-ops.sh, not directly):
--   osascript run-deck-ops.applescript <basePath> <outPath> <importSpec> <orderStr> <replaceStr>
--
-- Prerequisites:
--   * RunDeckOps.bas imported into an OPEN macro-enabled deck (e.g. DeckOps.pptm).
--   * VBA macros enabled in PowerPoint (Settings > Security).
--   * First run triggers a one-time macOS Automation-consent prompt
--     (System Settings > Privacy & Security > Automation) — approve it once.

on run argv
	if (count of argv) < 5 then
		error "Expected 5 args: basePath outPath importSpec orderStr replaceStr"
	end if
	set basePath to item 1 of argv
	set outPath to item 2 of argv
	set importSpec to item 3 of argv
	set orderStr to item 4 of argv
	set replaceStr to item 5 of argv

	tell application "Microsoft PowerPoint"
		activate
		set rc to run VB macro macro name "RunDeckOps" list of parameters {basePath, outPath, importSpec, orderStr, replaceStr}
	end tell
	return "RunDeckOps returned: " & rc
end run
