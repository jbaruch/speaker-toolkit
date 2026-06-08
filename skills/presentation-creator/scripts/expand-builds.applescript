-- expand-builds.applescript
-- Reads the packed build-expansion spec as UTF-8 and hands it to the ExpandBuilds
-- VBA macro, which replaces each progressive-reveal parent slide with its build
-- frames as full-bleed background-fill slides. Packed format: see RunDeckOps.bas
-- ExpandBuilds.
--   osascript expand-builds.applescript <basePath> <outPath> <packedSpecFile>
on run argv
	if (count of argv) < 3 then error "Expected 3 args: basePath outPath packedSpecFile"
	set basePath to item 1 of argv
	set outPath to item 2 of argv
	set packed to read (POSIX file (item 3 of argv)) as «class utf8»
	tell application "Microsoft PowerPoint"
		activate
		set rc to run VB macro macro name "ExpandBuilds" list of parameters {basePath, outPath, packed}
	end tell
	if rc < 0 then error "ExpandBuilds failed (rc=" & rc & ") — see the PowerPoint error dialog; confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "ExpandBuilds returned: " & rc
end run
