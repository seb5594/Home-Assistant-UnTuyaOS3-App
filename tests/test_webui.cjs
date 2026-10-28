"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

// Count actual rendering work for a large verbose OTA batch. No browser or
// hardware is needed: per-event text replacement previously stalled the UI.
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: "", writes: 0, scrollReads: 0, checked: true,
    classList: {toggle() {}}, replaceChildren() {}, append() {}, focus() {},
    get textContent() { return this.value; },
    set textContent(value) { this.value = value; this.writes++; },
    get scrollHeight() { this.scrollReads++; return 100; }
  });
  return elements.get(id);
}
const events = Array.from({length: 4000}, (_, index) => ({
  id: index+1, time: "2026-10-28T00:00:00Z", level: "info", channel: "terminal",
  text: "Sending OTA package: " + index + " " + "x".repeat(120) + "\n"
}));
const context = vm.createContext({
  document: {getElementById: element, querySelector: () => ({content: "test-token"}), createElement: () => element(Symbol())},
  Option: function(text, value) { this.text = text; this.value = value; },
  setInterval() {}, File: class {}, window: {confirm: () => true},
  fetch: async (path) => ({ok: true, json: async () => path === "api/firmware" ? {files: {}}
    : {state: "unconfirmed", exit_code: 3, events, cursor: 4000, generation: "new", adapters: [], usb_devices: [], host: {}}})
});
vm.runInContext(fs.readFileSync("untuyaos3/app/static/app.js", "utf8"), context);
setImmediate(() => {
  assert.equal(element("state").value, "unconfirmed");
  assert.match(element("notice").value, /device did not confirm/);
  assert.equal(element("terminal").writes, 2, "One reset and one batch render, not one write per frame");
  assert.equal(element("logs").writes, 2);
  assert.equal(element("terminal").scrollReads, 1);
  assert.equal(element("logs").scrollReads, 1);
  assert.ok(element("terminal").value.length <= 500000);
  assert.ok(element("logs").value.length <= 750000);
  console.log("PASS: 4000 OTA events render once per panel; unconfirmed status remains explicit");
});
