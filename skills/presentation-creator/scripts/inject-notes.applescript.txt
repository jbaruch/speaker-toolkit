-- inject-notes.applescript
-- Reads the packed speaker-notes file as UTF-8 and writes each note through
-- PowerPoint's AppleScript object model (`set content`), which carries Unicode
-- text intact. It does not call the SetSpeakerNotes VBA macro: `run VB macro`
-- converts its string parameters to the Mac Roman code page, so arrows, emoji
-- and every other character outside it reached the notes as "?".
-- Packed format: records separated by character id 30 (RS); within a record,
-- the 1-based slide number and the note text separated by character id 31 (US).
-- Opens basePath, saves the result to outPath, and closes it; basePath is not
-- modified.
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
		if (name of every presentation) contains baseName then error "ERROR: a presentation named " & baseName & " is already open — pass a uniquely-named copy."
		if (name of every presentation) contains outName then error "ERROR: a presentation named " & outName & " is already open — close it or choose another output name."
		with timeout of 1800 seconds
			open POSIX file basePath
		end timeout
		set p to presentation baseName
	end tell

	set applied to 0
	try
		set applied to my applyNotes(p, packed)
		tell application "Microsoft PowerPoint"
			with timeout of 1800 seconds
				save p in POSIX file outPath
			end timeout
			close presentation outName saving no
		end tell
	on error errMsg number errNum
		my closeIfOpen(baseName)
		my closeIfOpen(outName)
		error "ERROR: SetSpeakerNotes failed: " & errMsg number errNum
	end try
	return "SetSpeakerNotes returned: " & applied
end run

on applyNotes(p, packed)
	set RS to character id 30
	set US to character id 31
	set saved to AppleScript's text item delimiters
	set AppleScript's text item delimiters to RS
	set noteRecords to text items of packed
	set AppleScript's text item delimiters to saved
	set applied to 0
	repeat with recRef in noteRecords
		set rec to contents of recRef
		if length of rec > 0 then
			set usPos to offset of US in rec
			if usPos is 0 then error "Bad notes record (no unit separator): " & rec
			set num to (text 1 thru (usPos - 1) of rec) as integer
			if usPos is (length of rec) then
				set noteText to ""
			else
				set noteText to text (usPos + 1) thru -1 of rec
			end if
			tell application "Microsoft PowerPoint"
				set slideCount to count of slides of p
				if num < 1 or num > slideCount then error "Notes slide " & num & " out of range (deck has " & slideCount & ")"
				set s to slide num of p
			end tell
			my setNotesBody(s, noteText, num)
			set applied to applied + 1
		end if
	end repeat
	return applied
end applyNotes

-- Write noteText into the slide's notes body placeholder. Falls back to the
-- first text frame on the notes page that is not the title placeholder; a
-- notes page with neither raises instead of dropping the note.
on setNotesBody(s, noteText, num)
	tell application "Microsoft PowerPoint"
		set np to notes page of s
		set shapeCount to count of shapes of np
		repeat with i from 1 to shapeCount
			set sh to shape i of np
			if (shape type of sh) is shape type place holder then
				if (placeholder type of placeholder format of sh) is placeholder type body placeholder then
					set content of text range of text frame of sh to noteText
					return
				end if
			end if
		end repeat
		repeat with i from 1 to shapeCount
			set sh to shape i of np
			if has text frame of sh then
				if (shape type of sh) is not shape type place holder then
					set content of text range of text frame of sh to noteText
					return
				else if (placeholder type of placeholder format of sh) is not placeholder type title placeholder then
					set content of text range of text frame of sh to noteText
					return
				end if
			end if
		end repeat
	end tell
	error "slide " & num & " has no notes text frame"
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
