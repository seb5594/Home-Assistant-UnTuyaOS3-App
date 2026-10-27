"use strict";
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="csrf"]').content;
let cursor = 0, running = false, polling = false, lastState = "";
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
function controls(state) {
  running = state === "running";
  $("state").textContent = state;
  $("state").className = "badge " + state;
  $("start").disabled = !["ready", "finished", "cancelled", "failed"].includes(state);
  for (const id of ["choice", "send", "cancel"]) $(id).disabled = !running;
  $("upload").disabled = running;
}
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const response = await fetch("api/events?after=" + cursor);
    if (!response.ok) throw new Error("Ingress connection lost. Reopen the app from Home Assistant.");
    const data = await response.json();
    controls(data.state);
    $("adapter").textContent = data.adapter ? data.adapter.name + " · " + data.adapter.phy + " · isolated · AP-capable" : "No adapter";
    if (data.gap) append($("logs"), "\n[History truncated. Download the persistent logs for earlier output.]\n", logLimit);
    for (const event of data.events) {
      if (event.channel === "terminal") append($("terminal"), event.text, terminalLimit);
      append($("logs"), "[" + event.time + "] " + event.level.toUpperCase() + " · " + event.channel + "\n" + event.text + "\n", logLimit);
    }
    cursor = data.cursor;
    if (lastState !== data.state) {
      notice({ready: "Ready. Start a session, then answer the script's numbered prompts.",
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
