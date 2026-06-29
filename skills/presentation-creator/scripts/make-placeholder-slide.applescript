-- make-placeholder-slide.applescript
-- Calls the MakePlaceholderSlide VBA macro: build a 1-slide deck with a loud
-- yellow [PLACEHOLDER] slide (title + optional subtitle), sized to the base deck.
--   osascript make-placeholder-slide.applescript <basePath> <outPath> <title> <subtitle>
on run argv
	if (count of argv) < 4 then error "Expected 4 args: basePath outPath title subtitle"
	tell application "Microsoft PowerPoint"
		activate
		with timeout of 1800 seconds
			set rc to run VB macro macro name "MakePlaceholderSlide" list of parameters {item 1 of argv, item 2 of argv, item 3 of argv, item 4 of argv}
		end timeout
	end tell
	if (rc as string) starts with "ERROR" then error (rc as string) & " — confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "MakePlaceholderSlide returned: " & rc
end run
