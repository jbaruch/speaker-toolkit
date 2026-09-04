/* Offline crop review. Pure decision rules are exported for CI tests. */
"use strict";

const CropReview = (() => {
  const full = () => [0, 0, 1, 1];
  const validRegion = r => Array.isArray(r) && r.length === 4 &&
    r.every(v => typeof v === "number" && Number.isFinite(v)) &&
    0 <= r[0] && r[0] < r[2] && r[2] <= 1 &&
    0 <= r[1] && r[1] < r[3] && r[3] <= 1;
  const initial = talk => ({schema_version: 1, mode: talk.mode,
    region: talk.region.slice(), verdict: null});
  const key = batch => `crop-review-v1:${batch.id}:${batch.fingerprint}`;

  function validEntry(entry) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry) ||
        Object.keys(entry).sort().join(",") !== "mode,region,schema_version,verdict" ||
        entry.schema_version !== 1 || !validRegion(entry.region) ||
        !["crop", "full-frame", "no-slides"].includes(entry.mode)) return false;
    if (entry.mode !== "crop" && entry.region.some((v, i) => v !== full()[i])) return false;
    return entry.verdict === null ||
      (entry.verdict === "approved" && entry.mode !== "no-slides") ||
      (entry.verdict === "no-slides" && entry.mode === "no-slides");
  }

  function restore(talks, batch, raw) {
    const entries = Object.fromEntries(talks.map(t => [t.id, initial(t)]));
    if (raw === null) return entries;
    const saved = JSON.parse(raw);
    if (!saved || typeof saved !== "object" || saved.schema_version !== 1 ||
        Object.keys(saved).sort().join(",") !== "entries,fingerprint,schema_version" ||
        saved.fingerprint !== batch.fingerprint || !saved.entries ||
        typeof saved.entries !== "object" || Array.isArray(saved.entries) ||
        Object.keys(saved.entries).some(id => !Object.hasOwn(entries, id)) ||
        Object.values(saved.entries).some(e => !validEntry(e))) {
      throw new SyntaxError("Saved crop decisions do not match this reviewer");
    }
    for (const talk of talks) {
      if (Object.hasOwn(saved.entries, talk.id)) entries[talk.id] = saved.entries[talk.id];
    }
    return entries;
  }

  function edit(entry, region, mode = "crop") {
    const updated = {...entry, region: region.slice(), mode, verdict: null};
    if (!validEntry(updated)) throw new RangeError("Enter a rectangle inside the frame");
    return updated;
  }

  function approve(entry) {
    const updated = {...entry, region: entry.region.slice(),
      verdict: entry.mode === "no-slides" ? "no-slides" : "approved"};
    if (!validEntry(updated)) throw new RangeError("Review a valid region before approving");
    return updated;
  }

  function commands(talks, entries) {
    const lines = [];
    for (const talk of talks) {
      const entry = entries[talk.id];
      if (!validEntry(entry)) continue;
      if (entry.verdict === "approved") {
        lines.push(`${talk.command_prefix} --region ${entry.region.join(",")} --region-verified -- ${talk.id}`);
      } else if (entry.verdict === "no-slides") {
        // IDs are a closed alphabet; display titles never enter shell comments.
        lines.push(`# ${talk.id}: owner confirmed no slides; no extraction command`);
      }
    }
    return lines.join("\n");
  }

  function storageFailure(error) {
    return error instanceof SyntaxError ||
      (error instanceof DOMException && ["SecurityError", "QuotaExceededError"].includes(error.name));
  }

  function start(talks, batch) {
    const $ = id => document.getElementById(id);
    const announce = message => { $("notice").hidden = !message; $("notice").textContent = message; };
    let entries = restore(talks, batch, null);
    try { entries = restore(talks, batch, localStorage.getItem(key(batch))); }
    catch (error) {
      if (!storageFailure(error)) throw error;
      announce("Saved decisions could not be loaded. All proposals need approval again; copy your commands before closing this page.");
    }
    function save() {
      try { localStorage.setItem(key(batch), JSON.stringify({schema_version: 1,
        fingerprint: batch.fingerprint, entries})); }
      catch (error) {
        if (!storageFailure(error)) throw error;
        announce("Decisions are only in this open page. Browser storage is unavailable; copy the commands before closing.");
      }
    }

    let current = 0, frameIndex = 0, drag = null;
    const talk = () => talks[current];
    const entry = () => entries[talk().id];
    const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));
    const label = e => e.verdict === "approved" ? "Approved" :
      e.verdict === "no-slides" ? "Confirmed no slides" :
      e.mode === "no-slides" ? "Proposed no slides; not approved" : "Not approved";

    function renderList() {
      $("list").replaceChildren();
      for (const [index, item] of talks.entries()) {
        const button = document.createElement("button");
        button.className = "row";
        button.setAttribute("aria-current", index === current ? "true" : "false");
        const chip = document.createElement("span");
        chip.className = "chip " + (entries[item.id].verdict === "approved" ? "ok" : entries[item.id].verdict === "no-slides" ? "no" : "ed");
        chip.setAttribute("aria-hidden", "true");
        const name = document.createElement("span"); name.className = "nm";
        const title = document.createElement("span"); title.className = "t"; title.textContent = item.title;
        const detail = document.createElement("span"); detail.className = "c";
        detail.textContent = `${label(entries[item.id])} — ${item.conference || item.id}`;
        name.append(title, detail); button.append(chip, name);
        button.onclick = () => { current = index; frameIndex = 0; renderAll(); };
        $("list").append(button);
      }
      const approved = Object.values(entries).filter(e => e.verdict === "approved").length;
      const none = Object.values(entries).filter(e => e.verdict === "no-slides").length;
      $("cOk").textContent = approved; $("cNo").textContent = none;
      $("cLeft").textContent = talks.length - approved - none;
    }

    function renderCrop() {
      const [l, t, r, b] = entry().region;
      const crop = $("crop");
      crop.style.left = `${l * 100}%`; crop.style.top = `${t * 100}%`;
      crop.style.width = `${(r - l) * 100}%`; crop.style.height = `${(b - t) * 100}%`;
      crop.hidden = entry().mode === "no-slides";
      $("veil").hidden = crop.hidden;
      $("veil").style.clipPath = `polygon(0 0,100% 0,100% 100%,0 100%,0 0,${l*100}% ${t*100}%,${l*100}% ${b*100}%,${r*100}% ${b*100}%,${r*100}% ${t*100}%,${l*100}% ${t*100}%)`;
      ["iL", "iT", "iR", "iB"].forEach((id, i) => { $(id).value = entry().region[i]; });
      $("stateNote").textContent = label(entry());
      $("bOk").textContent = entry().mode === "no-slides" ? "Confirm no slides" : entry().mode === "full-frame" ? "Approve full frame" : "Approve crop";
    }

    function renderOut() {
      const output = commands(talks, entries);
      $("out").textContent = output || "Approve a decision to see its command or note.";
      $("bCopy").disabled = !output;
    }

    function renderAll() {
      const item = talk();
      $("tTitle").textContent = item.title;
      $("tConf").textContent = [item.conference, item.date].filter(Boolean).join(" / ");
      $("tId").textContent = item.id;
      $("tFrames").textContent = `${item.frames.length} individual sample frames`;
      $("tRatio").textContent = `Proposal: ${item.mode}`;
      $("img").src = item.frames[frameIndex].image;
      $("img").alt = `Frame at ${item.frames[frameIndex].timestamp.toFixed(2)} seconds: ${item.title}`;
      $("tabs").replaceChildren();
      item.frames.forEach((frame, index) => {
        const button = document.createElement("button"); button.className = "tab";
        button.textContent = `${frame.timestamp.toFixed(2)}s`;
        button.setAttribute("aria-pressed", index === frameIndex ? "true" : "false");
        button.onclick = () => { frameIndex = index; renderAll(); };
        $("tabs").append(button);
      });
      renderCrop(); renderList(); renderOut();
    }

    function setRegion(region, mode = "crop") {
      entries[talk().id] = edit(entry(), region, mode);
      save(); renderCrop(); renderList(); renderOut();
    }

    $("frame").addEventListener("pointerdown", event => {
      const handle = event.target.closest(".h");
      if (!handle && !event.target.closest(".crop")) return;
      event.preventDefault(); $("frame").focus();
      const rect = $("frame").getBoundingClientRect();
      drag = {mode: handle ? handle.dataset.h : "move", rect,
        x: event.clientX, y: event.clientY, start: entry().region.slice()};
      $("frame").setPointerCapture(event.pointerId);
    });
    $("frame").addEventListener("pointermove", event => {
      if (!drag) return;
      const dx = (event.clientX - drag.x) / drag.rect.width;
      const dy = (event.clientY - drag.y) / drag.rect.height;
      let [l, t, r, b] = drag.start;
      if (drag.mode === "move") {
        const w = r - l, h = b - t;
        l = clamp(l + dx, 0, 1 - w); t = clamp(t + dy, 0, 1 - h); r = l + w; b = t + h;
      } else {
        if (drag.mode.includes("w")) l = clamp(l + dx, 0, r - .001);
        if (drag.mode.includes("e")) r = clamp(r + dx, l + .001, 1);
        if (drag.mode.includes("n")) t = clamp(t + dy, 0, b - .001);
        if (drag.mode.includes("s")) b = clamp(b + dy, t + .001, 1);
      }
      if (validRegion([l, t, r, b])) setRegion([l, t, r, b]);
    });
    for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) {
      $("frame").addEventListener(event, () => { drag = null; });
    }

    ["iL", "iT", "iR", "iB"].forEach((id, index) => {
      $(id).addEventListener("change", () => {
        const region = entry().region.slice();
        region[index] = $(id).value === "" ? NaN : Number($(id).value);
        if (!validRegion(region)) {
          announce("Enter coordinates from 0 to 1, with left before right and top before bottom.");
          renderCrop(); return;
        }
        setRegion(region);
      });
    });
    $("frame").addEventListener("keydown", event => {
      const directions = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
      const direction = directions[event.key];
      if (!direction || entry().mode === "no-slides") return;
      event.preventDefault();
      const step = event.shiftKey ? .02 : .004;
      let [l, t, r, b] = entry().region;
      const w = r - l, h = b - t;
      l = clamp(l + direction[0] * step, 0, 1 - w);
      t = clamp(t + direction[1] * step, 0, 1 - h);
      setRegion([l, t, l + w, t + h]);
    });

    $("bOk").onclick = () => { entries[talk().id] = approve(entry()); save(); renderAll(); };
    $("bNo").onclick = () => { entries[talk().id] = approve(edit(entry(), full(), "no-slides")); save(); renderAll(); };
    $("bFull").onclick = () => setRegion(full(), "full-frame");
    $("bReset").onclick = () => { entries[talk().id] = initial(talk()); save(); renderAll(); };
    $("bClear").onclick = () => {
      if (confirm("Clear every decision in this reviewer?")) {
        entries = restore(talks, batch, null); save(); renderAll();
      }
    };
    $("bCopy").onclick = async () => {
      if (!navigator.clipboard) { announce("Clipboard access is unavailable. Select and copy the command text below."); return; }
      try {
        await navigator.clipboard.writeText(commands(talks, entries));
        announce("Commands copied. Nothing has been executed.");
      } catch (error) {
        if (!(error instanceof DOMException)) throw error;
        announce("Clipboard access was refused. Select and copy the command text below.");
      }
    };
    renderAll();
  }

  return {validRegion, initial, key, validEntry, restore, edit, approve, commands, start};
})();

if (typeof module !== "undefined" && module.exports) module.exports = CropReview;
if (typeof document !== "undefined") CropReview.start(TALKS, BATCH);
