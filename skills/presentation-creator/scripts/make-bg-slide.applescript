-- make-bg-slide.applescript
-- Calls the MakeBgImageSlide VBA macro: clone a comic template slide, swap its
-- background fill to an image, retitle, save a 1-slide deck.
--   osascript make-bg-slide.applescript <basePath> <templateNum> <imagePath> <title> <outPath>
on run argv
	if (count of argv) < 5 then error "Expected 5 args: basePath templateNum imagePath title outPath"
	tell application "Microsoft PowerPoint"
		activate
		set rc to run VB macro macro name "MakeBgImageSlide" list of parameters {item 1 of argv, item 2 of argv, item 3 of argv, item 4 of argv, item 5 of argv}
	end tell
	if rc < 0 then error "MakeBgImageSlide failed (rc=" & rc & ") — see the PowerPoint error dialog; confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "MakeBgImageSlide returned: " & rc
end run
