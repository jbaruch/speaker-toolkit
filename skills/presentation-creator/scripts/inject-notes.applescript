-- inject-notes.applescript
-- Writes each note into its slide's notes body placeholder through PowerPoint's
-- AppleScript object model (`set content`), which carries Unicode text intact.
-- Never `run VB macro`. The driver parses nothing: inject-notes.sh validates the
-- notes against the deck with notes-to-packed.py --driver-args and passes one
-- argument per slide, in slide order. An empty argument leaves that slide's notes
-- unchanged.
-- Opens basePath, saves the result to outPath, and closes it; basePath is not
-- modified. Each stage ([open], [slide N], [save], [close]) is logged to stderr
-- before it runs. Errors this driver raises name their stage and repair; any other
-- error propagates unchanged after the last logged stage, and inject-notes.sh adds
-- the repair.
--   osascript inject-notes.applescript <basePath> <outPath> [<note for slide 1>]...

property errAlreadyOpen : 1002
property errNoNotesBody : 1003
property errNotAuthorized : -1743

on run argv
	if (count of argv) < 2 then error "Expected: basePath outPath [note for slide 1]..."
	set basePath to item 1 of argv
	set outPath to item 2 of argv
	set baseName to my fileName(basePath)
	set outName to my fileName(outPath)

	log "[open] " & basePath
	-- AppleScript has no typed catch: this handler adds the repair for a denied
	-- Automation consent and re-raises every other error unchanged.
	try
		tell application "Microsoft PowerPoint"
			activate
			set openNames to name of every presentation
		end tell
	on error errMsg number errNum
		if errNum is errNotAuthorized then error "ERROR: inject-notes failed at [open]: " & errMsg & " — grant this terminal Automation access to Microsoft PowerPoint (System Settings > Privacy & Security > Automation; deck-editing-setup.md Step 4), then re-run." number errNum
		error errMsg number errNum
	end try
	-- PowerPoint keys open decks by filename: a same-named open deck would be
	-- returned instead of the file at basePath, or collide with the output.
	if openNames contains baseName then error "ERROR: inject-notes failed at [open]: a presentation named " & baseName & " is already open — pass a uniquely-named copy." number errAlreadyOpen
	if openNames contains outName then error "ERROR: inject-notes failed at [open]: a presentation named " & outName & " is already open — close it or choose another output name." number errAlreadyOpen
	tell application "Microsoft PowerPoint"
		with timeout of 1800 seconds
			open POSIX file basePath
		end timeout
		set p to presentation baseName
	end tell

	set applied to 0
	repeat with slideNumber from 3 to (count of argv)
		set noteText to item slideNumber of argv
		if noteText is not "" then
			log "[slide " & (slideNumber - 2) & "]"
			my setNotesBody(p, slideNumber - 2, noteText, baseName)
			set applied to applied + 1
		end if
	end repeat

	log "[save] " & outPath
	tell application "Microsoft PowerPoint"
		with timeout of 1800 seconds
			save p in POSIX file outPath
		end timeout
	end tell
	log "[close] " & outName
	tell application "Microsoft PowerPoint" to close presentation outName saving no
	return "Notes applied: " & applied
end run

-- Writes noteText into the notes body placeholder of slide num. A notes page
-- without one raises errNoNotesBody; the note never lands in a title, footer,
-- date, header or slide-number placeholder.
on setNotesBody(p, num, noteText, baseName)
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
	error "ERROR: inject-notes failed at [slide " & num & "]: the notes page has no notes body placeholder. The staged copy " & baseName & " is still open in PowerPoint: close it without saving, then in the source deck open View > Notes Master, enable Body under Placeholders, save, and re-run inject-notes.sh." number errNoNotesBody
end setNotesBody

on fileName(posixPath)
	set saved to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set nm to last text item of posixPath
	set AppleScript's text item delimiters to saved
	return nm
end fileName
