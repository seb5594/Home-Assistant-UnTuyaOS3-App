"use strict";
let lightleakVariants = [], lightleakDirty = true, lastLightleakState = "";
const lightleakFields = ["ll-chip", "ll-variant", "ll-ap-mode", "ll-writes", "ll-save", "ll-refresh"];
const originalPreparationHelp = $("preparation-help").textContent;
const originalRiskHelp = $("risk-ack").nextElementSibling.textContent;
const previousLightleakStatus = window.onSessionStatus;
window.onSessionStatus = (state, data) => {
  previousLightleakStatus(state, data);
  const active = data.tool === "lightleak";
  const busy = ["running", "assigning", "cleaning", "releasing", "offline"].includes(state)
    || Boolean(data.adapter_busy || data.selection_locked || breakerPending || startPending);
  $("lightleak-settings").hidden = !active;
  $("kickstart-help").hidden = active;
  $("preparation-help").textContent = active ? "Confirm the target chip, wipe its SmartLife pairing data and restore AP pairing mode. Lightleak setup writes device flash before creating a backup. Follow the console's power-cycle prompts." : originalPreparationHelp;
  $("risk-ack").nextElementSibling.textContent = active ? "I understand that Lightleak setup changes target flash and may permanently brick this device. I accept responsibility for using this tool." : originalRiskHelp;
  if (state === "running" && lastLightleakState !== "running") $("ll-writes").checked = false;
  $("firmware-library").hidden = active;
  $("open-firmware").parentElement.hidden = active;
  for (const id of lightleakFields) $(id).disabled = busy;
  for (const button of document.querySelectorAll(".ll-delete")) button.disabled = busy;
  if (active && (lightleakDirty || breakerPending || !data.engine_ready)) {
    $("start").disabled = true;
    $("start-help").textContent = "Review the Lightleak configuration and acknowledge its target-flash writes first.";
  }
  const review = data.lightleak_review;
  $("ll-review").textContent = review
    ? (!data.engine_ready ? "Review required for another attempt. Last selection: " : lightleakDirty ? "Unsaved changes. Previously reviewed: " : "Reviewed: ")
      + [review.variant, review.ap_mode, review.operation].join(" · ")
    : "No Lightleak configuration reviewed yet.";
  if (active && state !== lastLightleakState && !busy) refreshLightleak().catch((error) => notice(error.message, true));
  lastLightleakState = state;
};
function dirtyLightleak() {
  lightleakDirty = true;
  $("risk-ack").checked = false;
  breakerControls();
}
function renderLightleakVariants() {
  const selected = $("ll-variant").value;
  const matches = lightleakVariants.filter((item) => item.chip === $("ll-chip").value);
  $("ll-variant").replaceChildren(new Option(matches.length ? "Choose a generic variant…" : "Choose the chip first…", ""));
  for (const variant of matches) $("ll-variant").append(new Option(variant.name, variant.slug));
  if (matches.some((v) => v.slug === selected)) $("ll-variant").value = selected;
}
async function refreshLightleak() {
  const response = await fetch("api/lightleak");
  if (!response.ok) throw new Error("Lightleak metadata unavailable; check app diagnostics.");
  const data = await response.json();
  lightleakVariants = data.variants;
  renderLightleakVariants();
  const list = $("ll-backups");
  list.replaceChildren();
  if (!data.backups.length) list.textContent = "No complete backups yet.";
  for (const backup of data.backups) {
    if (!/^[0-9a-f]{32}$/.test(backup.id)) continue;
    const row = document.createElement("div"), info = document.createElement("p");
    row.className = "ll-backup";
    info.textContent = backup.chip + " · " + new Date(backup.created*1000).toLocaleString() + " · 2 MiB";
    const hash = document.createElement("p"); hash.className = "hint"; hash.textContent = "SHA-256: " + backup.sha256;
    const link = document.createElement("a"); link.className = "button secondary";
    link.href = "api/lightleak/backups/" + backup.id;
    link.download = "lightleak-" + backup.chip + "-" + backup.id + ".bin";
    link.textContent = "Download private dump";
    const remove = document.createElement("button"); remove.type = "button";
    remove.className = "secondary ll-delete"; remove.textContent = "Delete backup";
    const confirm = document.createElement("button"); confirm.type = "button";
    confirm.className = "danger ll-delete"; confirm.textContent = "Permanently delete this backup"; confirm.hidden = true;
    remove.onclick = () => { confirm.hidden = !confirm.hidden; };
    confirm.onclick = async () => {
      try { await breakerRequest("api/lightleak/backups/delete", {id: backup.id}); await refreshLightleak(); }
      catch (error) { notice(error.message, true); }
    };
    row.append(info, hash, link, remove, confirm); list.append(row);
  }
  // Lock newly created delete controls without recursively invoking a status refresh.
  const busy = ["running", "assigning", "cleaning", "releasing", "offline"].includes(currentState)
    || Boolean(currentStatus.adapter_busy || currentStatus.selection_locked || breakerPending || startPending);
  for (const button of document.querySelectorAll(".ll-delete")) button.disabled = busy;
}
$("ll-chip").onchange = () => { renderLightleakVariants(); $("ll-writes").checked = false; dirtyLightleak(); };
$("ll-variant").onchange = () => { $("ll-writes").checked = false; dirtyLightleak(); };
$("ll-writes").onchange = dirtyLightleak;
$("ll-ap-mode").onchange = () => {
  $("ll-ap-help").textContent = $("ll-ap-mode").value === "linux"
    ? "The app temporarily switches this isolated radio to AP mode. No ESP or VM is needed. Driver/target timing is unvalidated on real devices; an AP startup check runs before target writes."
    : "Install the CustomAP release image on your spare ESP with a graphical flasher. Power it on and check for LightleakIdle. Reset the companion before every new attempt. The app handles Wi-Fi and TCP configuration.";
  $("ll-writes").checked = false; dirtyLightleak();
};
$("ll-form").onsubmit = async (event) => {
  event.preventDefault();
  if ($("ll-save").disabled) return;
  try {
    if (!$("ll-variant").value || !$("ll-writes").checked) throw new Error("Select the confirmed chip and variant, then acknowledge target-flash writes.");
    await breakerRequest("api/lightleak/configure", {variant: $("ll-variant").value,
      ap_mode: $("ll-ap-mode").value, understand_writes: $("ll-writes").checked});
    lightleakDirty = false; $("ll-configuration").open = false; $("risk-ack").checked = false;
    await poll(); breakerControls();
    notice("Lightleak configuration reviewed. Confirm the general device risk before starting; follow the console prompts.");
  } catch (error) { dirtyLightleak(); notice(error.message, true); }
};
$("ll-refresh").onclick = () => refreshLightleak().catch((error) => notice(error.message, true));
refreshLightleak().catch(() => {});
