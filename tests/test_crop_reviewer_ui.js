/* Exercise browser event wiring with deterministic DOM/storage/clipboard ports. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../skills/vault-ingress/scripts/crop-reviewer.js"), "utf8");

function fixture({storageError = false, clipboardError = false, saved = null} = {}) {
  const nodes = new Map();
  class Element {
    constructor() { this.children = []; this.style = {}; this.handlers = {}; this.attributes = {}; this.value = ""; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    focus() { document.activeElement = this; }
    getBoundingClientRect() { return {width: 1000, height: 500}; }
    setPointerCapture() {}
  }
  const document = {activeElement: null,
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); },
    createElement() { return new Element(); }};
  const talks = [
    {schema_version: 1, id: "dQw4w9WgXcQ", title: "Diagram talk", conference: "ExampleConf", date: "2025-01-01", region: [.1,.2,.8,.9], mode: "crop", command_prefix: "python extract.py",
      frames: Array.from({length: 12}, (_, index) => ({schema_version: 1, timestamp: index + 1, image: `data:image/jpeg;base64,frame${index}`}))},
    {schema_version: 1, id: "abcdefghijk", title: "Discussion", conference: "ExampleConf", date: "2025-01-01", region: [0,0,1,1], mode: "no-slides", command_prefix: "python other.py",
      frames: Array.from({length: 6}, (_, index) => ({schema_version: 1, timestamp: index + 1, image: `data:image/jpeg;base64,other${index}`}))},
  ];
  const batch = {schema_version: 1, id: "fixture", fingerprint: "a".repeat(64)};
  let stored = saved, copied = null;
  const localStorage = {getItem() { if (storageError) throw new DOMException("denied", "SecurityError"); return stored; },
    setItem(key, value) { if (storageError) throw new DOMException("full", "QuotaExceededError"); stored = value; }};
  const navigator = {clipboard: {async writeText(value) { if (clipboardError) throw new DOMException("denied", "NotAllowedError"); copied = value; }}};
  const sandbox = {document, localStorage, navigator, DOMException, TALKS: talks, BATCH: batch, confirm: () => true};
  vm.runInNewContext(source, sandbox);
  return {get: id => nodes.get(id), stored: () => stored, copied: () => copied};
}

test("every timestamp is reachable; edits clear approval and output immediately", async () => {
  const ui = fixture();
  assert.equal(ui.get("tabs").children.length, 12);
  assert.equal(ui.get("cLeft").textContent, 2);
  assert.equal(ui.get("bCopy").disabled, true);
  ui.get("tabs").children[11].onclick();
  assert.equal(ui.get("img").src, "data:image/jpeg;base64,frame11");
  ui.get("bOk").onclick();
  assert.equal(ui.get("cOk").textContent, 1);
  assert.match(ui.get("out").textContent, /--region-verified/);
  await ui.get("bCopy").onclick();
  assert.equal(ui.copied(), ui.get("out").textContent);
  assert.match(ui.get("notice").textContent, /Nothing has been executed/);
  ui.get("iL").value = ".2";
  ui.get("iL").handlers.change();
  assert.equal(ui.get("cOk").textContent, 0);
  assert.equal(ui.get("stateNote").textContent, "Not approved");
  assert(!ui.get("out").textContent.includes("--region-verified"));
  ui.get("bOk").onclick();
  const persisted = fixture({saved: ui.stored()});
  assert.equal(persisted.get("cOk").textContent, 1);
  ui.get("bFull").onclick();
  assert.equal(ui.get("cOk").textContent, 0);
  assert.equal(ui.get("bOk").textContent, "Approve full frame");
  ui.get("bOk").onclick();
  assert.match(ui.get("out").textContent, /--region 0,0,1,1 --region-verified/);
  ui.get("bReset").onclick();
  assert.equal(ui.get("cOk").textContent, 0);
});

test("no-slides proposal needs confirmation and never emits extraction", () => {
  const ui = fixture();
  ui.get("list").children[1].onclick();
  assert.equal(ui.get("tabs").children.length, 6);
  assert.equal(ui.get("cNo").textContent, 0);
  assert.equal(ui.get("crop").hidden, true);
  ui.get("bOk").onclick();
  assert.equal(ui.get("cNo").textContent, 1);
  assert.match(ui.get("out").textContent, /^# abcdefghijk:/);
  assert(!ui.get("out").textContent.includes("extract.py"));
  ui.get("bFull").onclick();
  assert.equal(ui.get("cNo").textContent, 0);
  assert.equal(ui.get("crop").hidden, false);
  ui.get("bNo").onclick();
  assert.equal(ui.get("cNo").textContent, 1);
  ui.get("bClear").onclick();
  assert.equal(ui.get("cNo").textContent, 0);
  assert.equal(ui.get("cLeft").textContent, 2);
});

test("pointer and focused-keyboard changes invalidate the command", () => {
  const ui = fixture();
  ui.get("bOk").onclick();
  let prevented = false;
  ui.get("frame").handlers.keydown({key: "ArrowRight", shiftKey: false, preventDefault() { prevented = true; }});
  assert(prevented);
  assert.equal(ui.get("cOk").textContent, 0);
  assert.equal(ui.get("iL").value, .10400000000000001);
  ui.get("bOk").onclick();
  const target = {closest(selector) { return selector === ".crop" ? {} : null; }};
  ui.get("frame").handlers.pointerdown({target, clientX: 100, clientY: 100, pointerId: 1, preventDefault() {}});
  ui.get("frame").handlers.pointermove({clientX: 150, clientY: 100});
  assert.equal(ui.get("cOk").textContent, 0);
  assert(ui.get("iL").value > .15);
  ui.get("frame").handlers.pointercancel();
  const value = ui.get("iL").value;
  ui.get("frame").handlers.pointermove({clientX: 900, clientY: 100});
  assert.equal(ui.get("iL").value, value);
});

test("invalid input, inaccessible storage, and refused clipboard are visible", async () => {
  const ui = fixture({storageError: true, clipboardError: true});
  assert.match(ui.get("notice").textContent, /could not be loaded/);
  ui.get("iL").value = "2";
  ui.get("iL").handlers.change();
  assert.match(ui.get("notice").textContent, /Enter coordinates/);
  assert.equal(ui.get("iL").value, .1);
  ui.get("bOk").onclick();
  assert.match(ui.get("notice").textContent, /only in this open page/);
  await ui.get("bCopy").onclick();
  assert.match(ui.get("notice").textContent, /Clipboard access was refused/);
  assert.equal(ui.copied(), null);
  const malformed = fixture({saved: "{broken"});
  assert.equal(malformed.get("cOk").textContent, 0);
  assert.match(malformed.get("notice").textContent, /could not be loaded/);
});
