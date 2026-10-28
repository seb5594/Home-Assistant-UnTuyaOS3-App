"use strict";
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="csrf"]').content;
let cursor = 0, running = false, polling = false, lastState = "";
let logGeneration = null, viewEpoch = 0, adapterView = "";
const terminalLimit = 500000, logLimit = 750000;
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
  running = state === "running";
  $("state").textContent = state;
  $("state").className = "badge " + state;
  $("start").disabled = !["ready", "finished", "cancelled", "failed"].includes(state) || Boolean(data.adapter_busy || data.recovery_pending) || !(data.selected_adapter || data.adapter);
  for (const id of ["choice", "send", "cancel"]) $(id).disabled = !running;
  $("upload").disabled = running;
  $("refresh-adapters").disabled = Boolean(data.adapter_busy) || state === "offline";
  $("adapter-select").disabled = Boolean(data.selection_locked || data.adapter_busy) || ["offline", "running", "assigning", "cleaning", "releasing"].includes(state);
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
    $("adapter").textContent = data.adapter ? data.adapter.name + " · " + data.adapter.phy + " · isolated · AP-capable" : data.selected_adapter ? data.selected_adapter + " · ready to assign on Start" : "Choose a Wi-Fi adapter above";
    if (logGeneration !== data.generation) {
      $("terminal").textContent = "";
      $("logs").textContent = "";
      logGeneration = data.generation;
    }
    if (data.gap) append($("logs"), "\n[History truncated. Download the persistent logs for earlier output.]\n", logLimit);
    for (const event of data.events) {
      if (event.channel === "terminal") append($("terminal"), event.text, terminalLimit);
      append($("logs"), "[" + event.time + "] " + event.level.toUpperCase() + " · " + event.channel + "\n" + event.text + "\n", logLimit);
    }
    cursor = data.cursor;
    if (lastState !== data.state) {
      notice({ready: "Ready. Start a session, then answer the script's numbered prompts.",
        select_adapter: data.adapter_error || "Select an eligible Wi-Fi adapter above. Start the helper first if discovery is unavailable.",
        assigning: "Checking and assigning the selected radio to this app…",
        releasing: "Returning the adapter and restoring its original host settings…",
        running: "Session active. Follow the console; submit a menu choice when prompted.",
        finished: "Script finished with exit code " + data.exit_code + ". Review the console and verify your device.",
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
  $("start").disabled = true;
  try { await api("api/start"); await poll(); $("choice").focus(); } catch (error) { notice(error.message, true); }
};
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
  try { await api("api/input", {choice: $("choice").value}); $("choice").value = ""; }
  catch (error) { notice(error.message, true); }
};
async function library() {
  const response = await fetch("api/firmware");
  if (!response.ok) return;
  const data = await response.json();
  $("library").textContent = Object.entries(data.files).map(([platform, files]) => platform + ": " + files.length + " image(s)").join(" · ");
}
$("firmware-form").onsubmit = async (event) => {
  event.preventDefault();
  const file = $("firmware").files[0];
  if (!file) return;
  $("upload").disabled = true;
  try {
    await api("api/firmware", file, {"Content-Type": "application/octet-stream",
      "X-Firmware-Platform": $("platform").value, "X-Firmware-Name": file.name});
    notice("Firmware uploaded. Select it from the script's menu in your next session.");
    $("firmware").value = ""; await library();
  } catch (error) { notice(error.message, true); }
  finally { $("upload").disabled = running; }
};
poll(); library().catch(() => {}); setInterval(poll, 1000);
