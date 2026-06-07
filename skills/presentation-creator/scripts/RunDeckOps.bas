Attribute VB_Name = "DeckOps"
' =====================================================================
' DeckOps  -  the deck-operations VBA module: RunDeckOps (trim/reorder/
' import/replace), MakeBgImageSlide, ApplyBackgrounds, SetSpeakerNotes,
' MakePlaceholderSlide, InsertQR, and BuildDeck (whole-deck creation).
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

' Build a 1-slide deck holding a bright-yellow placeholder slide (a loud
' [PLACEHOLDER] title + optional subtitle), sized to the base deck. Meant to be
' InsertFromFile'd into the deck at a position via run-deck-ops.sh's order string
' — Mac VBA's Slide.MoveTo raises E_INVALIDARG, so we build-then-assemble rather
' than insert-and-move. Replaces the python-pptx insert-placeholder-slides.py.
' Invoked via:
'   run VB macro macro name "MakePlaceholderSlide" list of parameters _
'       {basePath, outPath, titleText, subtitleText}
Public Function MakePlaceholderSlide(ByVal basePath As String, _
                                     ByVal outPath As String, _
                                     ByVal titleText As String, _
                                     ByVal subtitleText As String) As Long
    Dim curTok As String
    Dim base As Presentation
    ' outer-boundary-process-contract — see the module-header error-handling contract.
    On Error GoTo Fail6

    curTok = "guard:base"
    AssertNotOpen BaseName(basePath)
    curTok = "open:base"
    Set base = Presentations.Open(FileName:=basePath, WithWindow:=msoTrue)

    Dim sw As Single, sh As Single
    sw = base.PageSetup.SlideWidth
    sh = base.PageSetup.SlideHeight

    ' append a blank slide, remember it by stable SlideID
    curTok = "add-slide"
    Dim s As Slide
    Set s = base.Slides.Add(base.Slides.Count + 1, ppLayoutBlank)
    Dim keepID As Long
    keepID = s.SlideID

    ' loud yellow full-bleed background
    curTok = "bg"
    Dim bgShape As Shape
    Set bgShape = s.Shapes.AddShape(msoShapeRectangle, 0, 0, sw, sh)
    bgShape.Fill.Solid
    bgShape.Fill.ForeColor.RGB = RGB(255, 242, 158)
    bgShape.Line.Visible = msoFalse

    ' [PLACEHOLDER]-prefixed title — centered, bold, 44pt
    curTok = "title"
    Dim ttl As String
    ttl = titleText
    If InStr(1, LTrim(ttl), "[PLACEHOLDER] ", vbTextCompare) <> 1 Then ttl = "[PLACEHOLDER] " & ttl
    Dim margin As Single
    margin = 36
    Dim tb As Shape
    Set tb = s.Shapes.AddTextbox(msoTextOrientationHorizontal, margin, sh / 3, sw - 2 * margin, 126)
    tb.TextFrame.WordWrap = msoTrue
    With tb.TextFrame.TextRange
        .Text = ttl
        .ParagraphFormat.Alignment = ppAlignCenter
        .Font.Size = 44
        .Font.Bold = msoTrue
        .Font.Color.RGB = RGB(32, 32, 32)
    End With

    ' optional subtitle — centered, 20pt
    If Len(subtitleText) > 0 Then
        curTok = "subtitle"
        Dim stb As Shape
        Set stb = s.Shapes.AddTextbox(msoTextOrientationHorizontal, margin, sh / 3 + 140, sw - 2 * margin, 200)
        stb.TextFrame.WordWrap = msoTrue
        With stb.TextFrame.TextRange
            .Text = subtitleText
            .ParagraphFormat.Alignment = ppAlignCenter
            .Font.Size = 20
            .Font.Color.RGB = RGB(64, 64, 64)
        End With
    End If

    ' trim to the placeholder slide only (compare by stable SlideID)
    curTok = "trim-to-one"
    Dim i As Long
    For i = base.Slides.Count To 1 Step -1
        If base.Slides(i).SlideID <> keepID Then base.Slides(i).Delete
    Next i

    curTok = "save"
    base.SaveCopyAs FileName:=outPath
    curTok = "close"
    base.Close
    MakePlaceholderSlide = 1
    Exit Function

Fail6:
    Dim em As String
    em = "MakePlaceholderSlide failed at [" & curTok & "]:" & vbCr & _
         Err.Number & " - " & Err.Description
    On Error Resume Next
    If Not base Is Nothing Then
        base.Saved = msoTrue
        base.Close
    End If
    On Error GoTo 0
    MsgBox em, vbCritical, "MakePlaceholderSlide"
    MakePlaceholderSlide = -1
End Function

' Insert a QR PNG bottom-right on the given 1-based slides, replacing any
' existing QR-sized picture already in that corner (idempotent re-runs).
' Replaces the python-pptx write in generate-qr.py — that script keeps the URL
' resolve + per-slide background-color match + PNG generation (reads only).
' Invoked via:
'   run VB macro macro name "InsertQR" list of parameters _
'       {basePath, outPath, pngPath, slideNumsCSV}
' slideNumsCSV = comma-separated 1-based slide numbers, e.g. "5,12".
Public Function InsertQR(ByVal basePath As String, _
                         ByVal outPath As String, _
                         ByVal pngPath As String, _
                         ByVal slideNumsCSV As String) As Long
    Dim curTok As String
    Dim base As Presentation
    ' outer-boundary-process-contract — see the module-header error-handling contract.
    On Error GoTo Fail7

    curTok = "guard:base"
    AssertNotOpen BaseName(basePath)
    curTok = "open:base"
    Set base = Presentations.Open(FileName:=basePath, WithWindow:=msoTrue)

    ' QR geometry mirrors generate-qr.py: 2.0in square, 0.3in margin, ~0.1in
    ' position/size tolerance for detecting an existing QR to replace (points).
    Const QR_SIDE As Single = 144
    Const QR_MARGIN As Single = 21.6
    Const TOL As Single = 7.2
    Dim sw As Single, sh As Single
    sw = base.PageSetup.SlideWidth
    sh = base.PageSetup.SlideHeight
    Dim qrLeft As Single, qrTop As Single
    qrLeft = sw - QR_SIDE - QR_MARGIN
    qrTop = sh - QR_SIDE - QR_MARGIN

    Dim nums() As String, k As Long, num As Long, placed As Long
    nums = Split(slideNumsCSV, ",")
    placed = 0
    For k = LBound(nums) To UBound(nums)
        If Len(Trim(nums(k))) > 0 Then
            num = CLng(Trim(nums(k)))
            curTok = "slide:" & num
            If num < 1 Or num > base.Slides.Count Then Err.Raise vbObjectError + 520, , _
                "QR slide " & num & " out of range (deck has " & base.Slides.Count & ")"
            Dim s As Slide
            Set s = base.Slides(num)
            ' remove an existing QR-sized picture in the bottom-right corner
            Dim i As Long, shp As Shape
            For i = s.Shapes.Count To 1 Step -1
                Set shp = s.Shapes(i)
                If shp.Type = msoPicture Then
                    If Abs(shp.Left - qrLeft) < TOL And Abs(shp.Top - qrTop) < TOL _
                       And Abs(shp.Width - QR_SIDE) < TOL Then
                        shp.Delete
                    End If
                End If
            Next i
            s.Shapes.AddPicture FileName:=pngPath, LinkToFile:=msoFalse, _
                SaveWithDocument:=msoTrue, Left:=qrLeft, Top:=qrTop, Width:=QR_SIDE, Height:=QR_SIDE
            placed = placed + 1
        End If
    Next k

    curTok = "save"
    base.SaveCopyAs FileName:=outPath
    curTok = "close"
    base.Close
    InsertQR = placed
    Exit Function

Fail7:
    Dim em As String
    em = "InsertQR failed at [" & curTok & "]:" & vbCr & _
         Err.Number & " - " & Err.Description
    On Error Resume Next
    If Not base Is Nothing Then
        base.Saved = msoTrue
        base.Close
    End If
    On Error GoTo 0
    MsgBox em, vbCritical, "InsertQR"
    InsertQR = -1
End Function

' Build a whole deck from a flat op sequence via the real PowerPoint app — the
' unified creation engine that retires strip-template.py + the MCP structural
' walk (add_slide / populate_placeholder / add_bullet_points / manage_text /
' manage_image / add_shape / add_table / add_chart / optimize_slide_text). Opens
' the template (for its custom layouts + masters), removes its demo slides, then
' executes the ops and saves a COPY. Layout/placeholder/content choices are the
' agent's judgment — it emits the ops; this only executes them.
'
' opsText is newline-separated; each line is "OP" then US(Chr31)-delimited args.
' AppleScript reads the ops file as UTF-8 and passes it as one Unicode arg.
' SLIDE starts a slide; subsequent ops apply to the current slide / table / chart.
' Geometry is in points. Ops:
'   SLIDE␟<0-based custom-layout index>
'   TITLE␟<text>   SUBTITLE␟<text>   BODY␟<text>   BULLET␟<0-based level>␟<text>
'   TEXT␟<l>␟<t>␟<w>␟<h>␟<text>      IMAGE␟<l>␟<t>␟<w>␟<h>␟<path>
'   SHAPE␟<msoAutoShapeType>␟<l>␟<t>␟<w>␟<h>      BG␟<r>␟<g>␟<b>      FOOTER␟<text>
'   TABLE␟<rows>␟<cols>␟<l>␟<t>␟<w>␟<h>   then CELL␟<1-based r>␟<c>␟<text> …
'   CHART␟<xlChartType>␟<l>␟<t>␟<w>␟<h>   then CAT␟<name> … and SERIES␟<name>␟<v>␟<v>… …
'   OPTIMIZE   (shrink current slide's text to fit its boxes)
' Invoked via:
'   run VB macro macro name "BuildDeck" list of parameters {basePath, outPath, opsText}
Public Function BuildDeck(ByVal basePath As String, _
                          ByVal outPath As String, _
                          ByVal opsText As String) As Long
    Dim curTok As String
    Dim base As Presentation
    ' outer-boundary-process-contract — see the module-header error-handling contract.
    On Error GoTo Fail8

    curTok = "guard:base"
    AssertNotOpen BaseName(basePath)
    curTok = "open:base"
    Set base = Presentations.Open(FileName:=basePath, WithWindow:=msoTrue)

    ' strip the template's demo slides (keeps masters + custom layouts) — subsumes strip-template.py
    curTok = "strip"
    Dim i As Long
    For i = base.Slides.Count To 1 Step -1
        base.Slides(i).Delete
    Next i
    Dim layouts As CustomLayouts
    Set layouts = base.SlideMaster.CustomLayouts

    Dim cur As Slide, curTbl As Table, curChart As Chart
    Dim catBuf As Collection, serBuf As Collection   ' chart accumulation (flushed on next CHART/SLIDE/end)
    Set catBuf = New Collection: Set serBuf = New Collection
    Dim lines() As String, li As Long, f() As String, op As String, ln As String, placed As Long
    lines = Split(opsText, vbLf)
    placed = 0
    For li = LBound(lines) To UBound(lines)
        ln = lines(li)
        If Len(ln) > 0 Then If Right(ln, 1) = vbCr Then ln = Left(ln, Len(ln) - 1)
        If Len(Trim(ln)) > 0 Then
            f = Split(ln, Chr(31))
            op = UCase(Trim(f(0)))
            curTok = "op:" & op & "#" & (li + 1)
            Select Case op
                Case "SLIDE"
                    FlushChart curChart, catBuf, serBuf: Set curChart = Nothing
                    Dim lay As Long
                    lay = CLng(f(1)) + 1
                    If lay < 1 Or lay > layouts.Count Then Err.Raise vbObjectError + 522, , _
                        "SLIDE layout index " & f(1) & " out of range (template has " & layouts.Count & " custom layouts)"
                    Set cur = base.Slides.AddSlide(base.Slides.Count + 1, layouts(lay))
                    Set curTbl = Nothing
                    placed = placed + 1
                Case "TITLE": SetPlaceholderText cur, ppPlaceholderTitle, f(1)
                Case "SUBTITLE": SetPlaceholderText cur, ppPlaceholderSubtitle, f(1)
                Case "BODY": SetPlaceholderText cur, ppPlaceholderBody, f(1)
                Case "BULLET": AddBulletLine cur, CLng(f(1)), f(2)
                Case "TEXT"
                    Dim tbx As Shape
                    Set tbx = cur.Shapes.AddTextbox(msoTextOrientationHorizontal, CSng(f(1)), CSng(f(2)), CSng(f(3)), CSng(f(4)))
                    tbx.TextFrame.WordWrap = msoTrue
                    tbx.TextFrame.TextRange.Text = f(5)
                Case "IMAGE"
                    cur.Shapes.AddPicture FileName:=f(5), LinkToFile:=msoFalse, SaveWithDocument:=msoTrue, _
                        Left:=CSng(f(1)), Top:=CSng(f(2)), Width:=CSng(f(3)), Height:=CSng(f(4))
                Case "SHAPE"
                    cur.Shapes.AddShape CLng(f(1)), CSng(f(2)), CSng(f(3)), CSng(f(4)), CSng(f(5))
                Case "BG"
                    cur.FollowMasterBackground = msoFalse
                    cur.Background.Fill.Solid
                    cur.Background.Fill.ForeColor.RGB = RGB(CLng(f(1)), CLng(f(2)), CLng(f(3)))
                Case "FOOTER"
                    Dim ft As Shape
                    Set ft = cur.Shapes.AddTextbox(msoTextOrientationHorizontal, 7, base.PageSetup.SlideHeight - 28, base.PageSetup.SlideWidth - 14, 22)
                    ft.TextFrame.TextRange.Text = f(1)
                    ft.TextFrame.TextRange.Font.Size = 10
                Case "OPTIMIZE": AutofitSlide cur
                Case "TABLE"
                    Set curTbl = cur.Shapes.AddTable(CLng(f(1)), CLng(f(2)), CSng(f(3)), CSng(f(4)), CSng(f(5)), CSng(f(6))).Table
                Case "CELL"
                    curTbl.Cell(CLng(f(1)), CLng(f(2))).Shape.TextFrame.TextRange.Text = f(3)
                Case "CHART"
                    FlushChart curChart, catBuf, serBuf
                    Set curChart = cur.Shapes.AddChart2(-1, CLng(f(1)), CSng(f(2)), CSng(f(3)), CSng(f(4)), CSng(f(5))).Chart
                Case "CAT": catBuf.Add f(1)
                Case "SERIES"
                    Dim sv As Collection, vi As Long
                    Set sv = New Collection
                    sv.Add f(1)                                  ' [1] = series name
                    For vi = 2 To UBound(f): sv.Add CDbl(f(vi)): Next vi  ' [2..] = values
                    serBuf.Add sv
                Case Else
                    Err.Raise vbObjectError + 521, , "Unknown BuildDeck op '" & op & "' on line " & (li + 1)
            End Select
        End If
    Next li
    FlushChart curChart, catBuf, serBuf   ' flush the last chart

    curTok = "save"
    base.SaveCopyAs FileName:=outPath
    curTok = "close"
    base.Close
    BuildDeck = placed
    Exit Function

Fail8:
    Dim em As String
    em = "BuildDeck failed at [" & curTok & "]:" & vbCr & _
         Err.Number & " - " & Err.Description
    On Error Resume Next
    If Not base Is Nothing Then
        base.Saved = msoTrue
        base.Close
    End If
    On Error GoTo 0
    MsgBox em, vbCritical, "BuildDeck"
    BuildDeck = -1
End Function

' Set a placeholder's text by type (ppPlaceholderTitle / Subtitle / Body). If the
' chosen layout lacks that placeholder, PRESERVE the content in a fallback text
' box (FallbackBox) rather than dropping it silently — the caller would otherwise
' report success on a deck missing the requested copy.
Private Sub SetPlaceholderText(ByVal sld As Slide, ByVal phType As Long, ByVal txt As String)
    If sld Is Nothing Then Exit Sub
    Dim shp As Shape
    For Each shp In sld.Shapes
        If shp.Type = msoPlaceholder Then
            If shp.PlaceholderFormat.Type = phType Then
                shp.TextFrame.TextRange.Text = txt
                Exit Sub
            End If
        End If
    Next shp
    ' placeholder absent — fall back so the content is never lost
    Select Case phType
        Case ppPlaceholderTitle
            Dim ttlShape As Shape
            Set ttlShape = Nothing
            On Error Resume Next
            Set ttlShape = sld.Shapes.Title
            On Error GoTo 0
            If ttlShape Is Nothing Then
                FallbackBox(sld, "Title").TextFrame.TextRange.Text = txt
            Else
                ttlShape.TextFrame.TextRange.Text = txt
            End If
        Case ppPlaceholderSubtitle
            FallbackBox(sld, "Subtitle").TextFrame.TextRange.Text = txt
        Case Else
            BodyTarget(sld).TextFrame.TextRange.Text = txt
    End Select
End Sub

' Append a bullet paragraph to the slide's body target at the given 0-based
' indent level. Uses the body/object placeholder when present, else a fallback
' text box (BodyTarget), so bullets are never dropped on a body-less layout.
Private Sub AddBulletLine(ByVal sld As Slide, ByVal level As Long, ByVal txt As String)
    If sld Is Nothing Then Exit Sub
    Dim body As Shape
    Set body = BodyTarget(sld)
    Dim tr As TextRange
    Set tr = body.TextFrame.TextRange
    If Len(tr.Text) > 0 Then tr.InsertAfter vbCr
    Dim para As TextRange
    Set para = tr.InsertAfter(txt)
    ' IndentLevel is a list property; guard it so a plain fallback box still keeps the text
    On Error Resume Next
    para.IndentLevel = level + 1
    On Error GoTo 0
End Sub

' The body/object placeholder if the layout has one, else a reused fallback text
' box so BODY + BULLET content survives a body-less layout.
Private Function BodyTarget(ByVal sld As Slide) As Shape
    Dim shp As Shape
    For Each shp In sld.Shapes
        If shp.Type = msoPlaceholder Then
            If shp.PlaceholderFormat.Type = ppPlaceholderBody _
               Or shp.PlaceholderFormat.Type = ppPlaceholderObject Then
                Set BodyTarget = shp: Exit Function
            End If
        End If
    Next shp
    Set BodyTarget = FallbackBox(sld, "Body")
End Function

' Create (or reuse) a named text box for content whose placeholder is missing
' from the chosen layout. One box per (slide, role); geometry is a sensible
' default band the author can reposition. Roles: "Title", "Subtitle", "Body".
Private Function FallbackBox(ByVal sld As Slide, ByVal role As String) As Shape
    Dim nm As String
    nm = "DeckOps_" & role
    Dim shp As Shape
    For Each shp In sld.Shapes
        If shp.Name = nm Then Set FallbackBox = shp: Exit Function
    Next shp
    Dim sw As Single, sh As Single, m As Single
    sw = sld.Parent.PageSetup.SlideWidth
    sh = sld.Parent.PageSetup.SlideHeight
    m = 36
    Dim t As Single, h As Single
    Select Case role
        Case "Title":    t = m:        h = sh * 0.18
        Case "Subtitle": t = sh * 0.2: h = sh * 0.12
        Case Else:       t = sh * 0.32: h = sh * 0.6
    End Select
    Set FallbackBox = sld.Shapes.AddTextbox(msoTextOrientationHorizontal, m, t, sw - 2 * m, h)
    FallbackBox.Name = nm
    FallbackBox.TextFrame.WordWrap = msoTrue
End Function

' Best-effort optimize_slide_text: shrink each text box's text to fit its shape.
Private Sub AutofitSlide(ByVal sld As Slide)
    If sld Is Nothing Then Exit Sub
    Dim shp As Shape
    For Each shp In sld.Shapes
        If shp.HasTextFrame Then
            On Error Resume Next
            shp.TextFrame2.WordWrap = msoTrue
            shp.TextFrame2.AutoSize = msoAutoSizeTextToFitShape
            On Error GoTo 0
        End If
    Next shp
End Sub

' Apply buffered categories + series to a chart, then clear the buffers. Series
' buffer items are Collections: [1]=name, [2..]=Double values. No-op if empty.
Private Sub FlushChart(ByVal ch As Chart, ByVal catBuf As Collection, ByVal serBuf As Collection)
    If ch Is Nothing Or serBuf.Count = 0 Then
        ClearCol catBuf: ClearCol serBuf
        Exit Sub
    End If
    ' categories array
    Dim cats() As Variant, ci As Long
    ReDim cats(1 To MaxL(catBuf.Count, 1))
    For ci = 1 To catBuf.Count: cats(ci) = catBuf(ci): Next ci
    ' drop the chart's default series, then add ours
    Do While ch.SeriesCollection.Count > 0
        ch.SeriesCollection(1).Delete
    Loop
    Dim si As Long, sv As Collection, sr As Series, vals() As Variant, vi As Long
    For si = 1 To serBuf.Count
        Set sv = serBuf(si)
        Set sr = ch.SeriesCollection.NewSeries
        sr.Name = sv(1)
        ReDim vals(1 To MaxL(sv.Count - 1, 1))
        For vi = 2 To sv.Count: vals(vi - 1) = sv(vi): Next vi
        sr.Values = vals
        If catBuf.Count > 0 Then sr.XValues = cats
    Next si
    ClearCol catBuf: ClearCol serBuf
End Sub

' Remove every item from a Collection (in place).
Private Sub ClearCol(ByVal c As Collection)
    Do While c.Count > 0: c.Remove 1: Loop
End Sub

' Larger of two Longs. PowerPoint VBA's Application has no Max (that is Excel's
' WorksheetFunction), so chart array sizing uses this instead.
Private Function MaxL(ByVal a As Long, ByVal b As Long) As Long
    If a > b Then MaxL = a Else MaxL = b
End Function

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
