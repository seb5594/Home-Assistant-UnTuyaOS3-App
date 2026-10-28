"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {webcrypto} = require("node:crypto");

// The Web UI script runs against a tiny fake DOM: no browser or hardware is needed.
// Elements are created on demand and count the writes that happen to them.
function loadUi(status, onPost = async () => ({})) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: "", writes: 0, scrollReads: 0, checked: true, hidden: false, href: "",
      classList: {toggle() {}}, replaceChildren() {}, append() {}, focus() {},
      get textContent() { return this.value; },
      set textContent(value) { this.value = value; this.writes++; },
      get scrollHeight() { this.scrollReads++; return 100; }
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    document: {getElementById: element, querySelector: () => ({content: "https://example.test/issues/new?template=device-report.yml"}),
               createElement: () => element(Symbol())},
    Option: function(text, value) { this.text = text; this.value = value; },
    setInterval() {}, File: class {}, window: {confirm: () => true}, crypto: webcrypto,
    fetch: async (path, options) => {
      if (options && options.method === "POST") {
        const result = await onPost(path, options);
        return {ok: true, json: async () => result};
      }
      return {ok: true, json: async () => path === "api/firmware" ? {files: {}}
        : {adapters: [], usb_devices: [], host: {}, ...status}};
    }
  });
  vm.runInContext(fs.readFileSync("untuyaos3/app/static/app.js", "utf8"), context);
  element.poll = () => vm.runInContext("poll()", context);
  return element;
}

// A verbose OTA can produce thousands of events. Per-event text replacement and
// scrolling once stalled the page, so a batch must be rendered once per panel.
function checkLargeBatch() {
  const events = Array.from({length: 4000}, (_, index) => ({
    id: index+1, time: "2026-10-28T00:00:00Z", level: "info", channel: "terminal",
    text: "Sending OTA package: " + index + " " + "x".repeat(120) + "\n"
  }));
  const element = loadUi({state: "unconfirmed", exit_code: 3, events, cursor: 4000, generation: "new"});
  return () => {
    assert.equal(element("state").value, "unconfirmed");
    assert.match(element("notice").value, /device did not confirm/);
    assert.equal(element("terminal").writes, 2, "One reset and one batch render, not one write per frame");
    assert.equal(element("logs").writes, 2);
    assert.equal(element("terminal").scrollReads, 1);
    assert.equal(element("logs").scrollReads, 1);
    assert.ok(element("terminal").value.length <= 500000);
    assert.ok(element("logs").value.length <= 750000);
    console.log("PASS: 4000 OTA events render once per panel; unconfirmed status remains explicit");
  };
}

// The helper card walks a new user through setup and shrinks once everything works.
function checkHelperCard() {
  const down = loadUi({state: "select_adapter", events: [], cursor: 0, generation: "g",
    helper: {state: "unreachable", message: "The Wi-Fi Helper is not running.", version: null}});
  const up = loadUi({state: "ready", events: [], cursor: 0, generation: "g",
    helper: {state: "ready", message: "Connected.", version: "1.0.0"}});
  return () => {
    assert.equal(down("helper-title").value, "Helper not running");
    assert.equal(down("helper-body").hidden, false);
    assert.equal(down("helper-steps").hidden, false);
    assert.match(down("helper-message").value, /not running/);
    assert.equal(up("helper-title").value, "Wi-Fi Helper connected · v1.0.0");
    assert.equal(up("helper-body").hidden, true, "A working helper needs no explanation");
    console.log("PASS: helper card explains setup and collapses when connected");
  };
}

// The generated pairing secret must be long enough for the apps and different every time.
function checkSecretGenerator() {
  const element = loadUi({state: "select_adapter", events: [], cursor: 0, generation: "g"});
  return () => {
    element("secret-generate").onclick();
    const first = element("secret-value").value;
    element("secret-generate").onclick();
    assert.match(first, /^[0-9a-f]{48}$/);
    assert.notEqual(element("secret-value").value, first);
    assert.equal(element("secret-box").hidden, false);
    console.log("PASS: pairing secret generator produces 48 random hex characters");
  };
}

// The device report link carries what the app already knows about the adapter.
function checkReportLink() {
  const element = loadUi({state: "ready", events: [], cursor: 0, generation: "g", selected_adapter: "wlan1",
    adapters: [{name: "wlan1", driver: "ath9k_htc", bus: "USB", eligible: true}],
    usb_devices: [{product: "UB91", id: "0cf3:9271", path: "1-1", drivers: ["ath9k_htc"], interfaces: ["wlan1"], assigned_interface: null}],
    host: {kernel: "6.18.52-haos"}});
  return () => {
    const href = element("report").href;
    assert.match(href, /^https:\/\/example\.test\/issues\/new\?template=device-report\.yml&wifi_adapter=/);
    assert.ok(href.includes(encodeURIComponent("UB91 (0cf3:9271), ath9k_htc, USB")), href);
    assert.ok(href.endsWith("&host_kernel=6.18.52-haos"), href);
    console.log("PASS: device report link is prefilled with adapter and kernel");
  };
}

const checks = [checkLargeBatch(), checkHelperCard(), checkSecretGenerator(), checkReportLink()];
const flush = () => new Promise((resolve) => setImmediate(resolve));
async function checkSessionSafety() {
  const status = {state: "ready", selected_adapter: "wlan1", events: [], cursor: 0, generation: "g"};
  let release, starts = 0, inputs = 0;
  const element = loadUi(status, async (path) => {
    if (path === "api/start") { starts++; await new Promise((resolve) => { release = resolve; }); }
    if (path === "api/input") { inputs++; await new Promise((resolve) => { release = resolve; }); }
    return {};
  });
  await flush();
  assert.equal(element("start").disabled, true, "No session without reviewing the risk");
  element("risk-ack").checked = true;
  element("risk-ack").onchange();
  assert.equal(element("start").disabled, false);
  status.selected_adapter = "wlan2";
  await element.poll();
  assert.equal(element("risk-ack").checked, false, "Changing radio requires a new review");
  element("risk-ack").checked = true;
  element("risk-ack").onchange();
  const start = element("start").onclick();
  await element("start").onclick();
  await element.poll();
  assert.equal(starts, 1, "A double tap or poll cannot submit another start");
  assert.equal(element("start").disabled, true);
  status.state = "running";
  release(); await start;
  assert.equal(element("risk-ack").checked, false);
  assert.equal(element("firmware").disabled, true);
  assert.equal(element("platform").disabled, true);
  element("choice").value = "2";
  const submit = element("choice-form").onsubmit({preventDefault() {}});
  await element("choice-form").onsubmit({preventDefault() {}});
  await element.poll();
  assert.equal(inputs, 1, "A double tap cannot answer the next menu by accident");
  assert.equal(element("send").disabled, true, "Polling must not unlock a pending input");
  release(); await submit;
  assert.equal(element("send").disabled, false);
  for (const state of ["cleaning", "releasing"]) {
    status.state = state; await element.poll();
    assert.equal(element("start").disabled, true);
    assert.equal(element("upload").disabled, true);
    assert.equal(element("adapter-select").disabled, true);
  }
  status.state = "finished"; await element.poll();
  assert.equal(element("start").disabled, true, "A completed session does not carry consent to the next");
  assert.equal(element("adapter-select").disabled, false);
  assert.equal(element("upload").disabled, false);
  element("open-firmware").onclick();
  assert.equal(element("firmware-library").open, true);
  console.log("PASS: per-attempt review, double-tap protection and cleanup controls");
}
setImmediate(async () => {
  try { checks.forEach((check) => check()); await checkSessionSafety(); }
  catch (error) { console.error(error); process.exitCode = 1; }
});
