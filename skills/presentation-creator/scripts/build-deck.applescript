-- build-deck.applescript
-- Reads the deck op-sequence file as UTF-8 and hands it to the BuildDeck VBA
-- macro, so VBA receives correct Unicode and never decodes UTF-8 from disk.
-- BuildDeck opens the template, strips its demo slides, and builds the deck.
--   osascript build-deck.applescript <templatePath> <outPath> <opsFile>
on run argv
	if (count of argv) < 3 then error "Expected 3 args: templatePath outPath opsFile"
	set ops to read (POSIX file (item 3 of argv)) as «class utf8»
	tell application "Microsoft PowerPoint"
		activate
		set rc to run VB macro macro name "BuildDeck" list of parameters {item 1 of argv, item 2 of argv, ops}
	end tell
	if rc < 0 then error "BuildDeck failed (rc=" & rc & ") — see the PowerPoint error dialog; confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "BuildDeck returned: " & rc
end run
