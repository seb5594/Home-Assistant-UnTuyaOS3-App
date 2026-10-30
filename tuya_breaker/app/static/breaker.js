"use strict";
const DEFAULT_ACCENT = "#7ac7ff", ACCENT_STORAGE = "tuya-breaker-accent-v1";
function applyAccent(value) {
  if (!/^#[0-9a-f]{6}$/i.test(value)) value = DEFAULT_ACCENT;
  const channels = [1, 3, 5].map((offset) => parseInt(value.slice(offset, offset+2), 16)/255);
  const linear = channels.map((c) => c <= .04045 ? c/12.92 : ((c+.055)/1.055)**2.4);
  const luminance = linear[0]*.2126+linear[1]*.7152+linear[2]*.0722;
  const root = document.documentElement;
  const highlight = luminance >= .3 ? value : "#" + channels.map((c) => Math.round((.55+c*.45)*255).toString(16).padStart(2,"0")).join("");
  root.style.setProperty("--cyan", highlight);
  root.style.setProperty("--accent-fill", value);
  root.style.setProperty("--button-text", luminance > .179 ? "#09131d" : "#ffffff");
  $("accent-colour").value = value;
  $("accent-value").textContent = value.toUpperCase();
  try { localStorage.setItem(ACCENT_STORAGE, value); } catch (_) { /* Ingress may restrict storage. */ }
}
let savedAccent = DEFAULT_ACCENT;
try { savedAccent = localStorage.getItem(ACCENT_STORAGE) || DEFAULT_ACCENT; } catch (_) {}
applyAccent(savedAccent);
$("accent-colour").oninput = () => applyAccent($("accent-colour").value);
$("accent-reset").onclick = () => applyAccent(DEFAULT_ACCENT);
let breakerDevices = [], breakerProfiles = [], breakerFirmware = {}, breakerDirty = true, breakerPending = false;
const ccFields = ["cc-search", "cc-device", "cc-profile", "cc-method", "cc-firmware", "cc-ssid", "cc-password", "cc-save", "cc-load", "cc-refresh"];
window.onSessionStatus = (state, data) => {
  const tool = data.tool || "untuyaos3";
  const busy = ["running", "assigning", "cleaning", "releasing", "offline"].includes(state)
    || Boolean(data.adapter_busy || data.selection_locked || breakerPending || startPending);
  for (const name of ["untuyaos3", "lightleak", "cloudcutter"]) {
    const button = $("tool-" + name);
    button.disabled = busy;
    button.setAttribute("aria-pressed", String(tool === name));
    button.classList.toggle("secondary", tool !== name);
  }
  $("cloudcutter-settings").hidden = tool !== "cloudcutter";
  $("tool-description").textContent = tool === "cloudcutter"
    ? "CloudCutter: select the exact original firmware profile, then flash or detach."
    : tool === "lightleak" ? "Lightleak: review a generic chip variant, install its payload and download a private flash backup."
    : "UnTuyaOS3: use the established platform and firmware menus.";
  for (const id of ccFields) $(id).disabled = busy;
  if (tool === "cloudcutter" && (breakerDirty || breakerPending || !data.engine_ready)) {
    $("start").disabled = true;
    $("start-help").textContent = "Review and use the CloudCutter configuration above before starting.";
  }
  const review = data.cloudcutter_review;
  $("cc-review").textContent = review
    ? (!data.engine_ready ? "Review required for a new attempt. Last selection: " : breakerDirty ? "Unsaved changes. Previously reviewed: " : "Reviewed: ")
      + [review.device, review.profile, review.chip, review.method, review.firmware].filter(Boolean).join(" · ")
    : "No CloudCutter configuration reviewed yet.";
};
function breakerControls() { controls(currentState, currentStatus); }
function dirtyBreaker() { breakerDirty = true; $("risk-ack").checked = false; breakerControls(); }
async function breakerRequest(path, data = {}) {
  if (breakerPending) throw new Error("Wait for the current configuration operation.");
  breakerPending = true; breakerControls();
  try { return await api(path, data); }
  finally { breakerPending = false; breakerControls(); }
}
for (const tool of ["untuyaos3", "lightleak", "cloudcutter"]) {
  $("tool-" + tool).onclick = async () => {
    if ($("tool-" + tool).disabled) return;
    $("risk-ack").checked = false;
    try { await breakerRequest("api/tool", {tool}); await poll(); }
    catch (error) { notice(error.message, true); }
  };
}
function renderCatalogue() {
  const selected = $("cc-device").value, query = $("cc-search").value.toLowerCase().trim();
  const matches = breakerDevices.filter((d) => (d.manufacturer + " " + d.name).toLowerCase().includes(query));
  $("cc-device").replaceChildren(new Option(matches.length > 200 ? "More than 200 matches — narrow your search…" : "Choose exact device and original firmware…", ""));
  for (const device of matches.slice(0, 200)) $("cc-device").append(new Option(device.manufacturer + " · " + device.name, device.slug));
  if (matches.slice(0, 200).some((d) => d.slug === selected)) $("cc-device").value = selected;
}
$("cc-search").oninput = () => { renderCatalogue(); dirtyBreaker(); };
$("cc-device").onchange = () => {
  breakerProfiles = [];
  $("cc-profile").replaceChildren(new Option("Load profiles for this device…", ""));
  renderFirmware(); dirtyBreaker();
};
$("cc-refresh").onclick = async () => {
  try {
    const result = await breakerRequest("api/cloudcutter/catalogue/refresh");
    breakerDevices = result.devices; renderCatalogue();
    notice("Official device catalogue loaded. Search for your exact model and original firmware.");
  } catch (error) { notice(error.message, true); }
};
$("cc-load").onclick = async () => {
  try {
    if (!$("cc-device").value) throw new Error("Choose a device first.");
    const result = await breakerRequest("api/cloudcutter/device", {device: $("cc-device").value});
    breakerProfiles = result.profiles;
    $("cc-profile").replaceChildren(new Option("Choose exact firmware profile…", ""));
    for (const profile of breakerProfiles) $("cc-profile").append(new Option(
      [profile.name, profile.firmware.name, profile.firmware.sdk].filter(Boolean).join(" · "), profile.slug));
    if (!breakerProfiles.length) notice("This device has no supported classic CloudCutter profile.", true);
    renderFirmware(); dirtyBreaker();
  } catch (error) { notice(error.message, true); }
};
function renderFirmware() {
  const name = $("cc-firmware").value;
  const profile = breakerProfiles.find((p) => p.slug === $("cc-profile").value);
  const chip = profile && profile.firmware.chip.toUpperCase();
  const files = breakerFirmware[chip] || [];
  $("cc-firmware").replaceChildren(new Option(chip ? "Choose a " + chip + " image…" : "Select an exact profile first…", ""));
  for (const file of files) $("cc-firmware").append(new Option(file, file));
  if (files.includes(name)) $("cc-firmware").value = name;
}
window.onFirmwareLibrary = (files) => { breakerFirmware = files; renderFirmware(); };
$("cc-profile").onchange = () => { renderFirmware(); dirtyBreaker(); };
for (const id of ["cc-firmware", "cc-ssid", "cc-password"]) $(id).oninput = dirtyBreaker;
$("cc-method").onchange = () => {
  $("cc-flash-settings").hidden = $("cc-method").value !== "flash";
  $("cc-detach-settings").hidden = $("cc-method").value !== "detach";
  dirtyBreaker();
};
$("cc-form").onsubmit = async (event) => {
  event.preventDefault();
  if ($("cc-save").disabled) return;
  try {
    await breakerRequest("api/cloudcutter/configure", {device: $("cc-device").value, profile: $("cc-profile").value,
      method: $("cc-method").value, firmware: $("cc-firmware").value,
      ssid: $("cc-ssid").value, password: $("cc-password").value});
    breakerDirty = false;
    $("cc-configuration").open = false;
    $("cc-password").value = "";
    $("risk-ack").checked = false;
    await poll(); breakerControls();
    notice("CloudCutter configuration reviewed. Check it, acknowledge the flashing risk, then start.");
  } catch (error) { dirtyBreaker(); notice(error.message, true); }
};
// A browser reload requires reviewing the form again; no Wi-Fi secret is returned.
fetch("api/cloudcutter/catalogue").then((r) => r.ok ? r.json() : {devices: []})
  .then((data) => { breakerDevices = data.devices; renderCatalogue(); }).catch(() => {});
fetch("api/firmware").then((r) => r.ok ? r.json() : {files: {}})
  .then((data) => window.onFirmwareLibrary(data.files)).catch(() => {});
breakerControls();
