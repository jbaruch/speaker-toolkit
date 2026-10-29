-- inject-notes.applescript
-- Reads the packed speaker-notes file as UTF-8 and writes each note into its
-- slide's notes body placeholder through PowerPoint's AppleScript object model
-- (`set content`), which carries Unicode text intact. Never `run VB macro`.
-- Packed format: records separated by character id 30 (RS); within a record,
-- the 1-based slide number and the note text separated by character id 31 (US).
-- Opens basePath, saves the result to outPath, and closes it; basePath is not
-- modified. Every failure names its stage (open, slide N, save) and the repair.
--   osascript inject-notes.applescript <basePath> <outPath> <packedNotesFile>
on run argv
	if (count of argv) < 3 then error "Expected 3 args: basePath outPath packedNotesFile"
	set basePath to item 1 of argv
	set outPath to item 2 of argv
	set packed to read (POSIX file (item 3 of argv)) as «class utf8»
	set baseName to my fileName(basePath)
	set outName to my fileName(outPath)

	tell application "Microsoft PowerPoint"
		activate
		-- PowerPoint keys open decks by filename: a same-named open deck would be
		-- returned instead of the file at basePath, or collide with the output.
		if (name of every presentation) contains baseName then error "ERROR: inject-notes failed at [open]: a presentation named " & baseName & " is already open — pass a uniquely-named copy."
		if (name of every presentation) contains outName then error "ERROR: inject-notes failed at [open]: a presentation named " & outName & " is already open — close it or choose another output name."
	end tell
	try
		tell application "Microsoft PowerPoint"
			with timeout of 1800 seconds
				open POSIX file basePath
			end timeout
			set p to presentation baseName
		end tell
	on error errMsg number errNum
		my closeIfOpen(baseName)
		error "ERROR: inject-notes failed at [open]: " & errMsg & " — confirm " & basePath & " exists inside PowerPoint's container (inject-notes.sh stages it) and that Automation consent is granted (deck-editing-setup.md Step 4)." number errNum
	end try

	try
		set applied to my applyNotes(p, packed)
	on error errMsg number errNum
		my closeIfOpen(baseName)
		error "ERROR: inject-notes failed at " & errMsg number errNum
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

-- Returns the number of notes written. Each error message starts with the
-- bracketed stage, so the caller can prefix it unchanged.
on applyNotes(p, packed)
	set RS to character id 30
	set US to character id 31
	set saved to AppleScript's text item delimiters
	set AppleScript's text item delimiters to RS
	set noteRecords to text items of packed
	set AppleScript's text item delimiters to saved
	tell application "Microsoft PowerPoint" to set slideCount to count of slides of p
	set applied to 0
	repeat with recRef in noteRecords
		set rec to contents of recRef
		if length of rec > 0 then
			set usPos to offset of US in rec
			if usPos is 0 then error "[parse]: notes record has no unit separator: " & (text 1 thru (my minimum(40, length of rec)) of rec) & " — regenerate the packed file with notes-to-packed.py."
			try
				set num to (text 1 thru (usPos - 1) of rec) as integer
			on error
				error "[parse]: notes record starts with a non-numeric slide number — regenerate the packed file with notes-to-packed.py."
			end try
			if num < 1 or num > slideCount then error "[slide " & num & "]: out of range, the deck has " & slideCount & " slides — rebuild notes.json against the post-expansion deck."
			if usPos is (length of rec) then
				set noteText to ""
			else
				set noteText to text (usPos + 1) thru -1 of rec
			end if
			try
				my setNotesBody(p, num, noteText)
			on error errMsg
				error "[slide " & num & "]: " & errMsg
			end try
			set applied to applied + 1
		end if
	end repeat
	return applied
end applyNotes

-- Writes noteText into the notes body placeholder of slide num. A notes page
-- without one raises; the note never lands in a title, footer, date, header or
-- slide-number placeholder.
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
	error "the notes page has no notes body placeholder — in PowerPoint open View > Notes Master, enable Body under Placeholders, save the deck, then re-run inject-notes.sh."
end setNotesBody

on closeIfOpen(deckName)
	tell application "Microsoft PowerPoint"
		if (name of every presentation) contains deckName then close presentation deckName saving no
	end tell
end closeIfOpen

on minimum(a, b)
	if a < b then return a
	return b
end minimum

on fileName(posixPath)
	set saved to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set nm to last text item of posixPath
	set AppleScript's text item delimiters to saved
	return nm
end fileName
