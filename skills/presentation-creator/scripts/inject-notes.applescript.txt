-- inject-notes.applescript
-- Writes each note into its slide's notes body placeholder through PowerPoint's
-- AppleScript object model (`set content`), which carries Unicode text intact.
-- Never `run VB macro`. The driver parses nothing: inject-notes.sh validates the
-- notes against the deck with notes-to-packed.py --driver-args and passes them
-- as argument pairs of 1-based slide number and note text.
-- Opens basePath, saves the result to outPath, and closes it; basePath is not
-- modified. Every failure names its stage (open, slide N, save), keeps the
-- original error number, and gives the repair.
--   osascript inject-notes.applescript <basePath> <outPath> [<slide #> <note text>]...

-- Error numbers this driver raises itself; anything else is PowerPoint's own.
property errUnpairedArgs : 1001
property errAlreadyOpen : 1002
property errNoNotesBody : 1003
property errNotAuthorized : -1743

on run argv
	if (count of argv) < 2 then error "Expected: basePath outPath [slideNumber noteText]..."
	set basePath to item 1 of argv
	set outPath to item 2 of argv
	if (count of argv) > 2 then
		set noteArgs to items 3 thru -1 of argv
	else
		set noteArgs to {}
	end if
	if ((count of noteArgs) mod 2) is not 0 then error "ERROR: inject-notes failed at [args]: slide numbers and note texts must come in pairs — run the driver through inject-notes.sh, which builds them with notes-to-packed.py --driver-args." number errUnpairedArgs
	set baseName to my fileName(basePath)
	set outName to my fileName(outPath)

	set openedByUs to false
	try
		tell application "Microsoft PowerPoint"
			activate
			set openNames to name of every presentation
		end tell
		-- PowerPoint keys open decks by filename: a same-named open deck would be
		-- returned instead of the file at basePath, or collide with the output.
		if openNames contains baseName then error "a presentation named " & baseName & " is already open — pass a uniquely-named copy." number errAlreadyOpen
		if openNames contains outName then error "a presentation named " & outName & " is already open — close it or choose another output name." number errAlreadyOpen
		tell application "Microsoft PowerPoint"
			with timeout of 1800 seconds
				open POSIX file basePath
			end timeout
			set openedByUs to true
			set p to presentation baseName
		end tell
	on error errMsg number errNum
		if openedByUs then my closeIfOpen(baseName)
		if errNum is errAlreadyOpen then error "ERROR: inject-notes failed at [open]: " & errMsg number errNum
		if errNum is errNotAuthorized then error "ERROR: inject-notes failed at [open]: " & errMsg & " — grant this terminal Automation access to Microsoft PowerPoint (System Settings > Privacy & Security > Automation; deck-editing-setup.md Step 4), then re-run." number errNum
		error "ERROR: inject-notes failed at [open]: " & errMsg & " — confirm " & basePath & " exists inside PowerPoint's container (inject-notes.sh stages it) and PowerPoint can open it, then re-run." number errNum
	end try

	set currentSlide to 0
	set applied to 0
	try
		repeat with i from 1 to (count of noteArgs) by 2
			set currentSlide to (item i of noteArgs) as integer
			my setNotesBody(p, currentSlide, item (i + 1) of noteArgs)
			set applied to applied + 1
		end repeat
	on error errMsg number errNum
		my closeIfOpen(baseName)
		if errNum is errNoNotesBody then error "ERROR: inject-notes failed at [slide " & currentSlide & "]: " & errMsg number errNum
		error "ERROR: inject-notes failed at [slide " & currentSlide & "]: PowerPoint refused the note: " & errMsg & " — open the deck in PowerPoint, check slide " & currentSlide & "'s notes page (View > Notes Page), then re-run inject-notes.sh." number errNum
	end try

	try
		tell application "Microsoft PowerPoint"
			with timeout of 1800 seconds
				save p in POSIX file outPath
			end timeout
		end tell
	on error errMsg number errNum
		my closeIfOpen(baseName)
		my closeIfOpen(outName)
		error "ERROR: inject-notes failed at [save]: " & errMsg & " — " & outPath & " must be inside PowerPoint's container; run the driver through inject-notes.sh, which stages the output." number errNum
	end try
	my closeIfOpen(outName)
	return "Notes applied: " & applied
end run

-- Writes noteText into the notes body placeholder of slide num. A notes page
-- without one raises errNoNotesBody; the note never lands in a title, footer,
-- date, header or slide-number placeholder.
on setNotesBody(p, num, noteText)
	tell application "Microsoft PowerPoint"
		set np to notes page of slide num of p
		repeat with i from 1 to (count of shapes of np)
			set sh to shape i of np
			if (shape type of sh) is shape type place holder then
				if (placeholder type of placeholder format of sh) is placeholder type body placeholder then
					set content of text range of text frame of sh to noteText
					return
				end if
			end if
		end repeat
	end tell
	error "the notes page has no notes body placeholder — in PowerPoint open View > Notes Master, enable Body under Placeholders, save the deck, then re-run inject-notes.sh." number errNoNotesBody
end setNotesBody

on closeIfOpen(deckName)
	tell application "Microsoft PowerPoint"
		if (name of every presentation) contains deckName then close presentation deckName saving no
	end tell
end closeIfOpen

on fileName(posixPath)
	set saved to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set nm to last text item of posixPath
	set AppleScript's text item delimiters to saved
	return nm
end fileName
