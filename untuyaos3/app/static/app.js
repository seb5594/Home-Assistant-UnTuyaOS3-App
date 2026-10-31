"use strict";
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="csrf"]').content;
let cursor = 0, running = false, polling = false, lastState = "";
let logGeneration = null, viewEpoch = 0, adapterView = "", helperView = "";
let currentState = "starting", currentStatus = {}, startPending = false, inputPending = false;
let reviewedAdapter = null, reviewedTool = null, uploadPending = false;
const terminalLimit = 500000, logLimit = 750000;
$("risk-ack").checked = false;
function append(element, text, limit) {
  element.textContent = (element.textContent + text).slice(-limit);
  if ($("follow").checked) element.scrollTop = element.scrollHeight;
}
function notice(text, error = false) {
  $("notice").textContent = text;
  $("notice").classList.toggle("error", error);
}
async function api(path, value = {}, headers = {}) {
  const response = await fetch(path, {method: "POST", headers: {"X-CSRF-Token": token,
    "Content-Type": "application/json", ...headers}, body: value instanceof File ? value : JSON.stringify(value)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}
function controls(state, data = {}) {
  // Acknowledgement belongs to one attempt. A later session must be reviewed again.
  const adapterName = data.selected_adapter || (data.adapter && data.adapter.name) || null;
  if ((state === "running" && currentState !== "running") || adapterName !== reviewedAdapter || (data.tool || null) !== reviewedTool)
    $("risk-ack").checked = false;
  currentState = state;
  currentStatus = data;
  running = state === "running";
  const busy = running || Boolean(data.adapter_busy || data.selection_locked)
    || ["assigning", "cleaning", "releasing"].includes(state);
  const ready = ["ready", "finished", "unconfirmed", "cancelled", "failed"].includes(state)
    && !busy && !uploadPending && data.engine_ready !== false && !data.recovery_pending && Boolean(data.selected_adapter || data.adapter);
  $("state").textContent = state.replace("_", " ");
  $("state").className = "badge " + state;
  $("start").disabled = !ready || !$("risk-ack").checked || startPending;
  $("risk-ack").disabled = busy || startPending || state === "offline";
  $("start-help").textContent = busy ? "Wait for this session and adapter cleanup to finish."
    : state === "offline" ? "Waiting for the app connection. Closing this page does not stop a session."
    : !ready ? "Resolve the helper or adapter status above before starting."
    : !$("risk-ack").checked ? "Acknowledge the flashing risk above to enable Start."
    : "Ready to start on " + (data.selected_adapter || data.adapter.name) + ".";
  for (const id of ["choice", "send"]) $(id).disabled = !running || inputPending;
  $("cancel").disabled = !running;
  for (const id of ["upload", "platform", "firmware"]) $(id).disabled = busy || startPending || uploadPending || state === "offline";
  $("refresh-adapters").disabled = Boolean(data.adapter_busy) || state === "offline";
  $("adapter-select").disabled = Boolean(data.selection_locked || data.adapter_busy) || ["offline", "running", "assigning", "cleaning", "releasing"].includes(state);
  if (typeof window.onSessionStatus === "function") window.onSessionStatus(state, data);
}
function showAdapters(data) {
  const key = JSON.stringify([data.adapters, data.usb_devices, data.host, data.selected_adapter, data.selection_locked, data.adapter_error]);
  if (key === adapterView) return;
  adapterView = key;
  const select = $("adapter-select");
  select.replaceChildren(new Option("Choose an eligible adapter…", ""));
  $("adapter-reasons").replaceChildren();
  for (const entry of data.adapters || []) {
    const label = [entry.name, entry.driver || "unknown driver", entry.bus || "", entry.leased ? "assigned" : ""].filter(Boolean).join(" · ");
    const option = new Option(label, entry.name);
    option.disabled = !entry.eligible;
    select.append(option);
    if (entry.reason && !entry.leased) {
      const reason = document.createElement("li");
      reason.textContent = entry.name + ": " + entry.reason;
      $("adapter-reasons").append(reason);
    }
  }
  select.value = data.selected_adapter || "";
  $("adapter-help").textContent = data.selection_locked
    ? "This radio is assigned to the active session. After the session ends and the radio is restored, selection unlocks automatically."
    : data.adapter_error || "One eligible adapter is selected automatically. Choose here when more than one is available.";
  $("usb-devices").replaceChildren();
  for (const entry of data.usb_devices || []) {
    const row = document.createElement("li");
    row.textContent = entry.product + " (" + entry.id + ", port " + entry.path + ") · driver: " + (entry.drivers.join(", ") || "not bound")
      + " · Wi-Fi interface: " + (entry.assigned_interface ? entry.assigned_interface + " (assigned to this app)" : entry.interfaces.join(", ") || "not present on host") + (entry.hint ? " — " + entry.hint : "");
    $("usb-devices").append(row);
  }
  if (!(data.usb_devices || []).length) {
    const row = document.createElement("li");
    row.textContent = "No USB Wi-Fi device found by the helper. Plug it in and refresh adapters.";
    $("usb-devices").append(row);
  }
  const host = data.host || {};
  $("host-drivers").textContent = host.kernel ? "Host kernel: " + host.kernel + " · Loaded Wi-Fi modules: "
    + ((host.loaded_wifi_modules || []).join(", ") || "none reported")
    + ". Loaded modules do not guarantee AP mode or successful flashing." : "Host driver information unavailable; refresh adapters.";
}
// Title, pill text and pill style per helper state (see HELPER_MESSAGES in devices.py).
const HELPER_STATES = {
  unknown: ["Looking for the helper…", "checking", ""],
  ready: ["Wi-Fi Helper connected", "connected", "ready"],
  outdated: ["Helper update needed", "update needed", "unconfirmed"],
  unreachable: ["Helper not running", "not running", "failed"],
  not_configured: ["Pairing secret missing", "setup needed", "failed"],
  pairing: ["Pairing secret mismatch", "mismatch", "failed"],
  protocol: ["Helper version mismatch", "mismatch", "failed"],
  error: ["Helper problem", "error", "failed"]
};
function showHelper(helper = {}) {
  const slug = typeof helper.addon_slug === "string" ? helper.addon_slug : "";
  $("helper-open").href = /^(?:[0-9a-f]{8}|local)_wifi_helper$/.test(slug)
    ? "https://my.home-assistant.io/redirect/supervisor_addon/?addon=" + encodeURIComponent(slug)
    : "https://my.home-assistant.io/redirect/supervisor_addons/";
  const key = JSON.stringify(helper);
  if (key === helperView) return;
  helperView = key;
  const state = HELPER_STATES[helper.state] ? helper.state : "unknown";
  const [title, pill, style] = HELPER_STATES[state];
  $("helper-title").textContent = title + (state === "ready" && helper.version ? " · v" + helper.version : "");
  $("helper-pill").textContent = pill;
  $("helper-pill").className = "badge " + style;
  $("helper-message").textContent = helper.message || "";
  // A working helper needs no explanation; keep the card to one line.
  $("helper-body").hidden = state === "ready";
  $("helper-steps").hidden = !["unknown", "unreachable", "not_configured"].includes(state);
}
// 24 random bytes as hex: 48 characters, comfortably above the 32 the apps require.
function generateSecret() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
// Prefill the GitHub issue form with what the app already knows about the adapter.
function updateReportLink(data) {
  const name = data.selected_adapter || (data.adapter && data.adapter.name);
  const entry = (data.adapters || []).find((adapter) => adapter.name === name);
  if (!entry) return;
  const usb = (data.usb_devices || []).find((device) => device.assigned_interface === name || device.interfaces.includes(name));
  const adapter = [usb ? usb.product + " (" + usb.id + ")" : "", entry.driver || "", entry.bus || ""].filter(Boolean).join(", ");
  const kernel = (data.host && data.host.kernel) || "";
  const base = document.querySelector('meta[name="report-url"]').content;
  $("report").href = base + "&wifi_adapter=" + encodeURIComponent(adapter) + "&host_kernel=" + encodeURIComponent(kernel);
}
async function poll() {
  if (polling) return;
  polling = true;
  const epoch = viewEpoch;
  try {
    const response = await fetch("api/events?after=" + cursor + (logGeneration ? "&generation=" + logGeneration : ""));
    if (!response.ok) throw new Error("Ingress connection lost. Reopen the app from Home Assistant.");
    const data = await response.json();
    if (epoch !== viewEpoch) return;
    controls(data.state, data);
    showAdapters(data);
    showHelper(data.helper);
    updateReportLink(data);
    $("adapter").textContent = data.adapter ? data.adapter.name + " · " + data.adapter.phy + " · isolated · AP-capable" : data.selected_adapter ? data.selected_adapter + " · ready to assign on Start" : "Choose a Wi-Fi adapter above";
    if (logGeneration !== data.generation) {
      $("terminal").textContent = "";
      $("logs").textContent = "";
      logGeneration = data.generation;
    }
    // Aggregate a whole poll before touching the DOM. Verbose OTA can produce
    // thousands of events; rewriting and scrolling per event stalls the page.
    const terminalParts = [], logParts = [];
    if (data.gap) logParts.push("\n[History truncated. Download the persistent logs for earlier output.]\n");
    for (const event of data.events) {
      if (event.channel === "terminal") terminalParts.push(event.text);
      logParts.push("[" + event.time + "] " + event.level.toUpperCase() + " · " + event.channel + "\n" + event.text + "\n");
    }
    if (terminalParts.length) append($("terminal"), terminalParts.join(""), terminalLimit);
    if (logParts.length) append($("logs"), logParts.join(""), logLimit);
    cursor = data.cursor;
    if (lastState !== data.state) {
      notice({ready: "Ready. Start a session, then answer the script's numbered prompts.",
        select_adapter: data.adapter_error || "Select an eligible Wi-Fi adapter above. Start the helper first if discovery is unavailable.",
        assigning: "Checking and assigning the selected radio to this app…",
        releasing: "Returning the adapter and restoring its original host settings…",
        running: "Session active. Follow the console; submit a menu choice when prompted.",
        finished: "Script finished with exit code " + data.exit_code + ". Review the console and verify your device.",
        unconfirmed: "The device did not confirm completion. Review the transfer log, check for Kickstart Wi-Fi and verify the device before attempting another flash.",
        cancelled: "Session stopped. Review the logs before trying again.",
        failed: "Session failed (exit " + data.exit_code + "). Review the diagnostics."}[data.state] || data.state,
        data.state === "failed");
      lastState = data.state;
    }
  } catch (error) {
    controls("offline");
    lastState = "";
    notice(error.message + " If the app stopped, open its Log tab for the final diagnostic.", true);
  } finally { polling = false; }
}
$("start").onclick = async () => {
  if ($("start").disabled || startPending) return;
  startPending = true;
  controls(currentState, currentStatus);
  try {
    await api("api/start");
    $("risk-ack").checked = false;
    await poll();
    // Do not pop up a phone's keyboard before there is a menu to answer.
    document.querySelector(".terminal-card")?.scrollIntoView?.({block: "start"});
  } catch (error) { notice(error.message, true); }
  finally { startPending = false; controls(currentState, currentStatus); }
};
$("risk-ack").onchange = () => {
  reviewedAdapter = currentStatus.selected_adapter || (currentStatus.adapter && currentStatus.adapter.name) || null;
  reviewedTool = currentStatus.tool || null;
  controls(currentState, currentStatus);
};
$("open-firmware").onclick = () => { $("firmware-library").open = true; };
$("refresh-adapters").onclick = async () => {
  $("refresh-adapters").disabled = true;
  try { await api("api/adapters/refresh"); await poll(); }
  catch (error) { notice(error.message, true); }
};
$("adapter-select").onchange = async () => {
  const selected = $("adapter-select").value;
  if (!selected) return;
  $("start").disabled = true;
  try { await api("api/adapters/select", {interface: selected}); await poll(); }
  catch (error) { adapterView = ""; notice(error.message, true); }
};
$("secret-generate").onclick = () => {
  $("secret-value").textContent = generateSecret();
  $("secret-box").hidden = false;
};
$("secret-copy").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("secret-value").textContent);
    notice("Pairing secret copied. Paste it into the Configuration tab of both apps.");
  } catch (error) {
    // Clipboard access can be blocked inside the Ingress frame; select the text instead.
    window.getSelection().selectAllChildren($("secret-value"));
    notice("Copying was blocked by the browser. The secret is selected; press Ctrl+C.", true);
  }
};
$("clear-logs").onclick = async () => {
  $("clear-logs").disabled = true;
  try {
    const result = await api("api/logs/clear");
    viewEpoch += 1; cursor = 0; logGeneration = result.generation;
    $("terminal").textContent = ""; $("logs").textContent = "";
    notice("Saved logs and both panels cleared. An active session continues.");
  } catch (error) { notice(error.message, true); }
  finally { $("clear-logs").disabled = false; }
};
$("cancel").onclick = async () => {
  if (!window.confirm("Stop the session? Interrupting a firmware upload may make the device unusable.")) return;
  try { await api("api/cancel"); } catch (error) { notice(error.message, true); }
};
$("choice-form").onsubmit = async (event) => {
  event.preventDefault();
  if (!running || inputPending) return;
  const choice = $("choice").value;
  if (!/^[0-9]{1,5}$/.test(choice)) { notice("Enter the numeric choice requested in the console.", true); return; }
  inputPending = true;
  controls(currentState, currentStatus);
  try { await api("api/input", {choice}); $("choice").value = ""; }
  catch (error) { notice(error.message, true); }
  finally { inputPending = false; controls(currentState, currentStatus); }
};
async function library() {
  const response = await fetch("api/firmware");
  if (!response.ok) return;
  const data = await response.json();
  $("library").textContent = Object.entries(data.files).map(([platform, files]) => platform + ": " + files.length + " image(s)").join(" · ");
  if (typeof window.onFirmwareLibrary === "function") window.onFirmwareLibrary(data.files);
}
$("firmware-form").onsubmit = async (event) => {
  event.preventDefault();
  if ($("upload").disabled || uploadPending) return;
  const file = $("firmware").files[0];
  if (!file) return;
  uploadPending = true;
  controls(currentState, currentStatus);
  try {
    await api("api/firmware", file, {"Content-Type": "application/octet-stream",
      "X-Firmware-Platform": $("platform").value, "X-Firmware-Name": file.name});
    notice("Firmware uploaded. Select it from the script's menu in your next session.");
    $("firmware").value = ""; await library();
  } catch (error) { notice(error.message, true); }
  finally { uploadPending = false; controls(currentState, currentStatus); }
};
poll(); library().catch(() => {}); setInterval(poll, 1000);
