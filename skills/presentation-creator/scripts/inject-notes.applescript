-- inject-notes.applescript
-- Writes each note into its slide's notes body placeholder through PowerPoint's
-- AppleScript object model (`set content`), which carries Unicode text intact.
-- Never `run VB macro`. The driver parses nothing: inject-notes.sh validates the
-- notes against the deck with notes-to-packed.py --driver-args and passes the
-- two deck file names, a marker path, and one argument per slide, in slide
-- order. An empty argument leaves that slide's notes unchanged. The driver
-- creates the marker file once PowerPoint has opened its own copy, so the
-- wrapper can tell that copy from a presentation that was already open.
-- Opens basePath, saves the result to outPath, and closes it; basePath is not
-- modified. Each stage ([open], [slide N], [save], [close]) is logged to stderr
-- before it runs. Errors this driver raises name their stage and repair; any other
-- error propagates unchanged after the last logged stage, and inject-notes.sh adds
-- the repair.
-- Before each stage it also writes that stage's token (open, slide N, save,
-- close) to stagePath, so the wrapper can give a stage-specific repair for an
-- error the driver did not raise itself.
--   osascript inject-notes.applescript <basePath> <outPath> <baseName> <outName> <markerPath> <stagePath> [<note for slide 1>]...

property errAlreadyOpen : 1002
property errNoNotesBody : 1003
property errNotAuthorized : -1743

on run argv
	if (count of argv) < 6 then error "Expected: basePath outPath baseName outName markerPath stagePath [note for slide 1]... — run the driver through inject-notes.sh."
	set basePath to item 1 of argv
	set outPath to item 2 of argv
	-- PowerPoint keys open decks by file name; the wrapper derives both names.
	set baseName to item 3 of argv
	set outName to item 4 of argv
	set markerPath to item 5 of argv
	set stagePath to item 6 of argv

	my recordStage(stagePath, "open")
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
	-- No presentation named baseName was open before, so this one is the run's
	-- own copy. The marker tells inject-notes.sh so if a later stage fails. Its
	-- creation is the only step here; whatever stops it (disk full, permissions,
	-- a missing folder), the copy is already open, so every failure carries
	-- that context and keeps its original error number.
	try
		close access (open for access (POSIX file markerPath) with write permission)
	on error errMsg number errNum
		error "ERROR: inject-notes failed at [open]: this run opened " & baseName & " but could not record that at " & markerPath & " (" & errMsg & ") — close " & baseName & " in PowerPoint without saving, free disk space or make that folder writable, and re-run." number errNum
	end try

	set applied to 0
	repeat with argIndex from 7 to (count of argv)
		set noteText to item argIndex of argv
		if noteText is not "" then
			my recordStage(stagePath, "slide " & (argIndex - 6))
			log "[slide " & (argIndex - 6) & "]"
			my setNotesBody(p, argIndex - 6, noteText, baseName)
			set applied to applied + 1
		end if
	end repeat

	my recordStage(stagePath, "save")
	log "[save] " & outPath
	tell application "Microsoft PowerPoint"
		with timeout of 1800 seconds
			save p in POSIX file outPath
		end timeout
	end tell
	my recordStage(stagePath, "close")
	log "[close] " & outName
	tell application "Microsoft PowerPoint" to close presentation outName saving no
	return "Notes applied: " & applied
end run

-- Overwrites stagePath with one fixed stage token and a newline.
on recordStage(stagePath, token)
	do shell script "printf '%s\\n' " & quoted form of token & " > " & quoted form of stagePath
end recordStage

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
