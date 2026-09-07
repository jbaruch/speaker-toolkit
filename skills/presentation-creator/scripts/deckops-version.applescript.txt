-- deckops-version.applescript
-- Read-only probe: asks the RUNNING PowerPoint which build of the DeckOps macro
-- is loaded, and where the macro container is open from. Drives no edit, opens
-- no file, saves nothing. Invoked by deckops-doctor.py, not directly.
--
-- Why this exists: a saved .pptm gives up no VBA source, so nothing on disk can
-- tell whether the module inside DeckOps.pptm matches the shipped RunDeckOps.bas.
-- The stamp travels INSIDE the module (DECKOPS_STAMP, written by
-- sync-deck-drivers.py stamp) and comes back through this call.
--
-- Never launches PowerPoint: a diagnostic that starts a 300 MB app as a side
-- effect is worse than the answer it returns.
--
-- Emits `key=value` lines on stdout (values may contain "=" and ";"; keys never do):
--   state=not_running                        PowerPoint is not open
--   state=macro_unreachable + detail=<msg>   no DeckOps.pptm open, macros off, or
--                                            the module was never imported
--   state=ok + stamp=<hex> + container=<path>
-- Exits 0 in every one of those cases — an unreachable macro is a finding to
-- report, not a failure of the probe. Nonzero only when osascript itself fails.

on run argv
	if not (application "Microsoft PowerPoint" is running) then
		return "state=not_running"
	end if

	-- Plural accessors on purpose. `repeat with p in presentations` + `name of p`
	-- raises -2763 ("no result was returned") on current Mac PowerPoint builds;
	-- `name of every presentation` returns the list correctly. Using the working
	-- form needs no error handler, so nothing here swallows a failure.
	set containerPath to ""
	tell application "Microsoft PowerPoint"
		set openNames to name of every presentation
		set openPaths to full name of every presentation
	end tell
	repeat with i from 1 to (count of openNames)
		if (item i of openNames) as string is "DeckOps.pptm" then
			set containerPath to (item i of openPaths) as string
		end if
	end repeat

	try
		tell application "Microsoft PowerPoint"
			with timeout of 60 seconds
				set macroStamp to run VB macro macro name "DeckOpsVersion"
			end timeout
		end tell
	on error errMsg number errNum
		-- One documented expected number: -18, which is what Mac PowerPoint returns
		-- when the named macro is not available (module never imported, macros
		-- disabled, or the container not open). Verified by running this probe
		-- against a PowerPoint with DeckOps.pptm open and no DeckOps module in it.
		-- Everything else -- a user cancel, a modal block, an unexpected failure --
		-- propagates, and deckops-doctor.py reports the non-zero osascript exit
		-- with its stderr as the detail.
		if errNum is not -18 then error errMsg number errNum
		set out to "state=macro_unreachable" & linefeed & "detail=" & errMsg
		if containerPath is not "" then set out to out & linefeed & "container=" & containerPath
		return out
	end try

	set out to "state=ok" & linefeed & "stamp=" & (macroStamp as string)
	if containerPath is not "" then set out to out & linefeed & "container=" & containerPath
	return out
end run
