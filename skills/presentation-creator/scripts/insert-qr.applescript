-- insert-qr.applescript
-- Calls the InsertQR VBA macro: place a QR PNG bottom-right on the given 1-based
-- slides (replacing any existing corner QR), then save a COPY.
--   osascript insert-qr.applescript <basePath> <outPath> <pngPath> <slideNumsCSV>
on run argv
	if (count of argv) < 4 then error "Expected 4 args: basePath outPath pngPath slideNumsCSV"
	tell application "Microsoft PowerPoint"
		activate
		set rc to run VB macro macro name "InsertQR" list of parameters {item 1 of argv, item 2 of argv, item 3 of argv, item 4 of argv}
	end tell
	if rc < 0 then error "InsertQR failed (rc=" & rc & ") — see the PowerPoint error dialog; confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "InsertQR returned: " & rc
end run
