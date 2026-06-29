-- insert-qr.applescript
-- Calls the InsertQR VBA macro: place a QR PNG on the given slides (replacing any
-- existing QR in place per the spec), then save a COPY.
--   osascript insert-qr.applescript <basePath> <outPath> <pngPath> <slidesSpec>
on run argv
	if (count of argv) < 4 then error "Expected 4 args: basePath outPath pngPath slidesSpec"
	tell application "Microsoft PowerPoint"
		activate
		with timeout of 1800 seconds
			set rc to run VB macro macro name "InsertQR" list of parameters {item 1 of argv, item 2 of argv, item 3 of argv, item 4 of argv}
		end timeout
	end tell
	if (rc as string) starts with "ERROR" then error (rc as string) & " — confirm DeckOps.pptm is open with macros enabled and Automation consent granted."
	return "InsertQR returned: " & rc
end run
