-- inject-notes.applescript
-- Reads the packed speaker-notes file as UTF-8 and hands it to the SetSpeakerNotes
-- VBA macro, so VBA receives correct Unicode and never decodes UTF-8 from disk
-- itself. Packed format: see RunDeckOps.bas SetSpeakerNotes.
--   osascript inject-notes.applescript <basePath> <outPath> <packedNotesFile>
on run argv
	if (count of argv) < 3 then error "Expected 3 args: basePath outPath packedNotesFile"
	set basePath to item 1 of argv
	set outPath to item 2 of argv
	set packed to read (POSIX file (item 3 of argv)) as «class utf8»
	tell application "Microsoft PowerPoint"
		activate
		set rc to run VB macro macro name "SetSpeakerNotes" list of parameters {basePath, outPath, packed}
	end tell
	if rc < 0 then error "SetSpeakerNotes failed (rc=" & rc & ") — see the PowerPoint error dialog; confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "SetSpeakerNotes returned: " & rc
end run
