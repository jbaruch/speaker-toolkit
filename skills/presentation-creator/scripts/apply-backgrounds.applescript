-- apply-backgrounds.applescript
-- Calls the ApplyBackgrounds VBA macro: set per-slide BACKGROUND FILLS in bulk
-- from a "<1-based #>=/path[;#=/path2 ...]" spec, then save a COPY.
--   osascript apply-backgrounds.applescript <basePath> <outPath> <specStr>
on run argv
	if (count of argv) < 3 then error "Expected 3 args: basePath outPath specStr"
	tell application "Microsoft PowerPoint"
		activate
		set rc to run VB macro macro name "ApplyBackgrounds" list of parameters {item 1 of argv, item 2 of argv, item 3 of argv}
	end tell
	if rc < 0 then error "ApplyBackgrounds failed (rc=" & rc & ") — see the PowerPoint error dialog; confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "ApplyBackgrounds returned: " & rc
end run
