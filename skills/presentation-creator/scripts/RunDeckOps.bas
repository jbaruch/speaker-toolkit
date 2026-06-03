Attribute VB_Name = "DeckOps"
' =====================================================================
' DeckOps  -  the deck-operations VBA module: RunDeckOps (trim/reorder/
' import/replace), MakeBgImageSlide, and ApplyBackgrounds.
'
' One module, not three, on purpose: VBA has no package manager, the
' public macros share private helpers (BaseName / AliasPath / AssertNotOpen),
' and the module is imported as a single unit into the DeckOps.pptm macro
' container. Splitting into per-macro files would force multiple imports plus
' duplicated or cross-referenced helpers for no benefit. The "single-purpose
' script" rule targets composable CLI scripts; this is a cohesive macro library.
'
' RunDeckOps  -  reusable, non-corrupting, FORMATTING-PRESERVING deck
' trim / reorder / cross-deck import.
'
' Builds the target deck with Slides.InsertFromFile (the programmatic
' "Reuse Slides", keep-source-formatting). This preserves per-slide
' background images / full-bleed graphics — plain clipboard Paste does
' NOT (it applies destination formatting and strips slide backgrounds).
' Output is written by the real PowerPoint engine, stays Keynote-openable,
' and the originals are never modified.
'
' Invoked from AppleScript:
'   run VB macro macro name "RunDeckOps" list of parameters _
'       {basePath, outPath, importSpec, orderStr, replaceStr}
'
' Arguments (all text):
'   basePath    POSIX path to the base deck (opened as the build container,
'               so the output inherits its slide size + masters)
'   outPath     POSIX path to write the trimmed COPY (use a LOCAL path —
'               sandboxed PowerPoint can't create files in a Google Drive
'               File-Provider folder; the shell wrapper moves it to Drive)
'   importSpec  "" or "alias=/posix/path[;alias2=/posix/path2]"
'   orderStr    space-separated final sequence, e.g.
'               "BASE:1 BASE:2 voxxed:13 voxxed:14 BASE:49"
'               token = <alias>:<1-based slide number in that file>;
'               alias "BASE" = the base file.
'   replaceStr  "" or "find=>to||find2=>to2"  (global text replacements)
'
' Algorithm: open base (for correct slide size); InsertFromFile each
' wanted slide (base or import) appended at the end, in target order,
' keeping source formatting; delete the original leading block; apply
' text replacements; SaveCopyAs.
'
' ERROR-HANDLING CONTRACT (applies to every Public macro below):
' outer-boundary-process-contract — each Public macro is the OUTERMOST boundary,
' invoked from AppleScript which reads the return code, and the shell wrapper
' treats a MISSING output file as failure. VBA has no typed exception catching,
' so each macro uses a catch-all `On Error GoTo FailN`. Caller's silent-failure
' shape: no return code + no output file. What the catch emits: a MsgBox + a -1
' return so the caller observes the failure. Why propagation breaks the contract:
' an unhandled VBA error would leave the deck open with no return code and no
' output, silently breaking the AppleScript/shell failure signal.
' =====================================================================
Option Explicit

Public Function RunDeckOps(ByVal basePath As String, _
                           ByVal outPath As String, _
                           ByVal importSpec As String, _
                           ByVal orderStr As String, _
                           ByVal replaceStr As String) As Long
    Dim curTok As String
    Dim base As Presentation
    ' outer-boundary-process-contract — see the module-header error-handling contract.
    On Error GoTo Fail

    ' GUARD: PowerPoint keys open presentations by filename and would
    ' silently hand back an already-open same-named deck. Fail loud.
    curTok = "guard:base"
    AssertNotOpen BaseName(basePath)

    curTok = "open:base"
    Set base = Presentations.Open(FileName:=basePath, WithWindow:=msoTrue)
    If LCase(BaseName(base.FullName)) <> LCase(BaseName(basePath)) Then
        Err.Raise vbObjectError + 513, , "Opened '" & base.FullName & _
            "' but expected '" & basePath & "' — name collision."
    End If
    Dim nOrig As Long
    nOrig = base.Slides.Count

    ' --- build target sequence via InsertFromFile (keep source formatting) ---
    Dim tokens() As String, i As Long, tok As String, cp As Long
    Dim alias As String, num As Long, placed As Long, srcPath As String
    tokens = Split(Trim(orderStr), " ")
    placed = 0
    For i = LBound(tokens) To UBound(tokens)
        tok = Trim(tokens(i))
        If Len(tok) > 0 Then
            curTok = "insert:" & tok
            cp = InStr(tok, ":")
            alias = Left(tok, cp - 1)
            num = CLng(Mid(tok, cp + 1))
            If UCase(alias) = "BASE" Then
                srcPath = basePath
            Else
                srcPath = AliasPath(alias, importSpec)
            End If
            ' Insert slide #num from srcPath AFTER the current last slide.
            base.Slides.InsertFromFile srcPath, base.Slides.Count, num, num
            placed = placed + 1
        End If
    Next i

    ' --- delete the original leading block (descending) ---
    curTok = "delete-original-block"
    For i = nOrig To 1 Step -1
        base.Slides(i).Delete
    Next i

    ' --- global text replacements ---
    If Len(Trim(replaceStr)) > 0 Then
        Dim pairs() As String, k As Long, arrow As Long
        Dim findStr As String, toStr As String
        Dim s As Slide, shp As Shape, tr As TextRange
        curTok = "text-replace"
        pairs = Split(replaceStr, "||")
        For Each s In base.Slides
            For Each shp In s.Shapes
                If shp.HasTextFrame Then
                    If shp.TextFrame.HasText Then
                        Set tr = shp.TextFrame.TextRange
                        For k = LBound(pairs) To UBound(pairs)
                            arrow = InStr(pairs(k), "=>")
                            If arrow > 0 Then
                                findStr = Left(pairs(k), arrow - 1)
                                toStr = Mid(pairs(k), arrow + 2)
                                If InStr(tr.Text, findStr) > 0 Then
                                    tr.Text = Replace(tr.Text, findStr, toStr)
                                End If
                            End If
                        Next k
                    End If
                End If
            Next shp
        Next s
    End If

    ' --- write a COPY (bare SaveCopyAs; FileFormat/EmbedTrueTypeFonts enum
    '     args raise E_INVALIDARG on this Mac build; base is already .pptx) ---
    curTok = "save"
    base.SaveCopyAs FileName:=outPath

    curTok = "close"
    base.Close

    RunDeckOps = placed
    Exit Function

Fail:
    Dim em As String
    em = "RunDeckOps failed at [" & curTok & "]:" & vbCr & _
         Err.Number & " - " & Err.Description
    On Error Resume Next
    If Not base Is Nothing Then
        base.Saved = msoTrue
        base.Close
    End If
    On Error GoTo 0
    MsgBox em, vbCritical, "RunDeckOps"
    RunDeckOps = -1
End Function

' Create a 1-slide deck: clone a comic TEMPLATE slide (inherits the layout's
' halftone-dot overlay + the Bangers title box + the footer), swap its
' BACKGROUND FILL to imagePath, and retitle it. The result is meant to be
' InsertFromFile'd into the deck, so the dot pattern covers the image like the
' rest of the comic slides (a top-pasted picture would sit ABOVE the overlay).
' Invoked via:
'   run VB macro macro name "MakeBgImageSlide" list of parameters _
'       {basePath, templateNum, imagePath, titleText, outPath}
Public Function MakeBgImageSlide(ByVal basePath As String, _
                                 ByVal templateNum As String, _
                                 ByVal imagePath As String, _
                                 ByVal titleText As String, _
                                 ByVal outPath As String) As Long
    Dim curTok As String
    Dim base As Presentation
    ' outer-boundary-process-contract — see the module-header error-handling contract.
    On Error GoTo Fail2

    curTok = "guard:base"
    AssertNotOpen BaseName(basePath)
    curTok = "open:base"
    Set base = Presentations.Open(FileName:=basePath, WithWindow:=msoTrue)

    ' clone the template slide (same-deck Duplicate preserves layout, overlay,
    ' title box, footer, and background-fill mechanism)
    curTok = "duplicate-template"
    Dim dupRange As SlideRange
    Set dupRange = base.Slides(CLng(templateNum)).Duplicate
    Dim s As Slide
    Set s = dupRange(1)
    Dim keepID As Long
    keepID = s.SlideID

    ' swap the slide BACKGROUND to the image — a true bg picture fill, so the
    ' layout's dot overlay covers it like the other comic slides
    curTok = "set-background"
    s.FollowMasterBackground = msoFalse
    s.Background.Fill.UserPicture imagePath

    ' retitle: first non-footer text box, keep Bangers
    curTok = "set-title"
    Dim shp As Shape, didTitle As Boolean
    didTitle = False
    For Each shp In s.Shapes
        If Not didTitle Then
            If shp.HasTextFrame Then
                If shp.TextFrame.HasText Then
                    If InStr(LCase(shp.TextFrame.TextRange.Text), "jbaruch") = 0 Then
                        shp.TextFrame.TextRange.Text = titleText
                        shp.TextFrame.TextRange.Font.Name = "Bangers"
                        didTitle = True
                    End If
                End If
            End If
        End If
    Next shp

    ' delete every slide except the clone (compare by stable SlideID)
    curTok = "trim-to-one"
    Dim i As Long
    For i = base.Slides.Count To 1 Step -1
        If base.Slides(i).SlideID <> keepID Then base.Slides(i).Delete
    Next i

    curTok = "save"
    base.SaveCopyAs FileName:=outPath
    curTok = "close"
    base.Close
    MakeBgImageSlide = 1
    Exit Function

Fail2:
    Dim em As String
    em = "MakeBgImageSlide failed at [" & curTok & "]:" & vbCr & _
         Err.Number & " - " & Err.Description
    On Error Resume Next
    If Not base Is Nothing Then
        base.Saved = msoTrue
        base.Close
    End If
    On Error GoTo 0
    MsgBox em, vbCritical, "MakeBgImageSlide"
    MakeBgImageSlide = -1
End Function

' Set per-slide BACKGROUND FILLS in bulk — the creation-time counterpart of
' MakeBgImageSlide. Each illustration becomes the slide's background (not a
' top-pasted picture shape), so the layout's halftone-dot overlay covers it
' and a python-pptx round-trip can't drop it. Run this as the FINAL write of
' the build pipeline (after structure / scrim / title / notes), since any
' later python-pptx save would re-drop the <p:bg> fills.
' Invoked via:
'   run VB macro macro name "ApplyBackgrounds" list of parameters _
'       {basePath, outPath, specStr}
' specStr = "<1-based slide #>=/posix/path[;<#>=/posix/path2 ...]"
Public Function ApplyBackgrounds(ByVal basePath As String, _
                                 ByVal outPath As String, _
                                 ByVal specStr As String) As Long
    Dim curTok As String
    Dim base As Presentation
    ' outer-boundary-process-contract — see the module-header error-handling contract.
    On Error GoTo Fail3

    curTok = "guard:base"
    AssertNotOpen BaseName(basePath)
    curTok = "open:base"
    Set base = Presentations.Open(FileName:=basePath, WithWindow:=msoTrue)

    Dim pairs() As String, k As Long, eq As Long
    Dim num As Long, imgPath As String, applied As Long
    Dim s As Slide
    pairs = Split(Trim(specStr), ";")
    applied = 0
    For k = LBound(pairs) To UBound(pairs)
        If Len(Trim(pairs(k))) > 0 Then
            eq = InStr(pairs(k), "=")
            If eq = 0 Then Err.Raise vbObjectError + 516, , _
                "Bad spec token (need '#=path'): " & pairs(k)
            num = CLng(Trim(Left(pairs(k), eq - 1)))
            imgPath = Trim(Mid(pairs(k), eq + 1))
            curTok = "bg:" & num
            If num < 1 Or num > base.Slides.Count Then Err.Raise vbObjectError + 517, , _
                "Slide " & num & " out of range (deck has " & base.Slides.Count & ")"
            Set s = base.Slides(num)
            s.FollowMasterBackground = msoFalse
            s.Background.Fill.UserPicture imgPath
            applied = applied + 1
        End If
    Next k

    curTok = "save"
    base.SaveCopyAs FileName:=outPath
    curTok = "close"
    base.Close
    ApplyBackgrounds = applied
    Exit Function

Fail3:
    Dim em As String
    em = "ApplyBackgrounds failed at [" & curTok & "]:" & vbCr & _
         Err.Number & " - " & Err.Description
    On Error Resume Next
    If Not base Is Nothing Then
        base.Saved = msoTrue
        base.Close
    End If
    On Error GoTo 0
    MsgBox em, vbCritical, "ApplyBackgrounds"
    ApplyBackgrounds = -1
End Function

' Set per-slide speaker notes via real PowerPoint, which serializes valid notes
' OOXML — so the <p:notesMasterIdLst> Keynote-compat hack python-pptx needed is
' unnecessary. AppleScript reads the notes file as UTF-8 and passes the packed
' text here as ONE Unicode argument (so VBA never has to decode UTF-8 from disk).
' Packed format: records separated by Chr(30) (RS); within a record, the 1-based
' slide number and the note text separated by Chr(31) (US). Both are non-printing
' control chars that do not occur in prose notes.
' Invoked via:
'   run VB macro macro name "SetSpeakerNotes" list of parameters _
'       {basePath, outPath, packedNotes}
Public Function SetSpeakerNotes(ByVal basePath As String, _
                                ByVal outPath As String, _
                                ByVal packedNotes As String) As Long
    Dim curTok As String
    Dim base As Presentation
    ' outer-boundary-process-contract — see the module-header error-handling contract.
    On Error GoTo Fail4

    curTok = "guard:base"
    AssertNotOpen BaseName(basePath)
    curTok = "open:base"
    Set base = Presentations.Open(FileName:=basePath, WithWindow:=msoTrue)

    Dim records() As String, i As Long, us As Long, applied As Long
    Dim num As Long, noteText As String
    applied = 0
    If Len(packedNotes) > 0 Then
        records = Split(packedNotes, Chr(30))
        For i = LBound(records) To UBound(records)
            If Len(records(i)) > 0 Then
                us = InStr(records(i), Chr(31))
                If us = 0 Then Err.Raise vbObjectError + 518, , _
                    "Bad notes record (no unit separator): " & records(i)
                num = CLng(Left(records(i), us - 1))
                noteText = Mid(records(i), us + 1)
                curTok = "set-notes:" & num
                If num < 1 Or num > base.Slides.Count Then Err.Raise vbObjectError + 519, , _
                    "Notes slide " & num & " out of range (deck has " & base.Slides.Count & ")"
                SetNotesBody base.Slides(num), noteText
                applied = applied + 1
            End If
        Next i
    End If

    curTok = "save"
    base.SaveCopyAs FileName:=outPath
    curTok = "close"
    base.Close
    SetSpeakerNotes = applied
    Exit Function

Fail4:
    Dim em As String
    em = "SetSpeakerNotes failed at [" & curTok & "]:" & vbCr & _
         Err.Number & " - " & Err.Description
    On Error Resume Next
    If Not base Is Nothing Then
        base.Saved = msoTrue
        base.Close
    End If
    On Error GoTo 0
    MsgBox em, vbCritical, "SetSpeakerNotes"
    SetSpeakerNotes = -1
End Function

' Write noteText into a slide's notes body placeholder (creating the notes page
' on access). Prefers the body placeholder; falls back to the first text frame
' on the notes page that is not the slide-image placeholder.
Private Sub SetNotesBody(ByVal s As Slide, ByVal noteText As String)
    Dim shp As Shape
    ' Prefer the notes body placeholder.
    For Each shp In s.NotesPage.Shapes
        If shp.Type = msoPlaceholder Then
            If shp.PlaceholderFormat.Type = ppPlaceholderBody Then
                shp.TextFrame.TextRange.Text = noteText
                Exit Sub
            End If
        End If
    Next shp
    ' Fallback: first non-title text frame. Guard the PlaceholderFormat access —
    ' it raises on non-placeholder shapes — so a recovery attempt never throws.
    For Each shp In s.NotesPage.Shapes
        If shp.HasTextFrame Then
            If shp.Type <> msoPlaceholder Then
                shp.TextFrame.TextRange.Text = noteText
                Exit Sub
            ElseIf shp.PlaceholderFormat.Type <> ppPlaceholderTitle Then
                shp.TextFrame.TextRange.Text = noteText
                Exit Sub
            End If
        End If
    Next shp
End Sub

' Filename portion of a POSIX path.
Private Function BaseName(ByVal p As String) As String
    Dim k As Long
    k = InStrRev(p, "/")
    If k = 0 Then BaseName = p Else BaseName = Mid(p, k + 1)
End Function

' Resolve an import alias to its file path from "a=/p1;b=/p2".
Private Function AliasPath(ByVal alias As String, ByVal importSpec As String) As String
    Dim specs() As String, j As Long, eq As Long
    specs = Split(importSpec, ";")
    For j = LBound(specs) To UBound(specs)
        eq = InStr(specs(j), "=")
        If eq > 0 Then
            If LCase(Trim(Left(specs(j), eq - 1))) = LCase(alias) Then
                AliasPath = Trim(Mid(specs(j), eq + 1))
                Exit Function
            End If
        End If
    Next j
    Err.Raise vbObjectError + 515, , "Unknown import alias '" & alias & "'"
End Function

' Raise a clear error if a presentation with this filename is already open.
Private Sub AssertNotOpen(ByVal fileName As String)
    Dim pp As Presentation
    For Each pp In Application.Presentations
        If LCase(pp.Name) = LCase(fileName) Then
            Err.Raise vbObjectError + 514, , "A presentation named '" & fileName & _
                "' is already open in PowerPoint. Close it (without saving) and re-run."
        End If
    Next pp
End Sub
