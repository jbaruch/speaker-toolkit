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

	set containerPath to ""
	try
		tell application "Microsoft PowerPoint"
			repeat with p in presentations
				if (name of p) is "DeckOps.pptm" then
					set containerPath to (full name of p) as string
				end if
			end repeat
		end tell
	on error
		-- A dictionary surprise here costs the container path, never the stamp.
		set containerPath to ""
	end try

	try
		tell application "Microsoft PowerPoint"
			with timeout of 60 seconds
				set macroStamp to run VB macro macro name "DeckOpsVersion"
			end timeout
		end tell
	on error errMsg
		return "state=macro_unreachable" & linefeed & "detail=" & errMsg
	end try

	set out to "state=ok" & linefeed & "stamp=" & (macroStamp as string)
	if containerPath is not "" then set out to out & linefeed & "container=" & containerPath
	return out
end run
