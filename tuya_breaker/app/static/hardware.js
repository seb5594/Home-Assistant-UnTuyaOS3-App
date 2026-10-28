"use strict";
let hardwareDevices = [], hardwarePage = 0, hardwareTimer, hardwareBusy = false;
const HARDWARE_PAGE_SIZE = 6;
const previousStatus = window.onSessionStatus;
window.onSessionStatus = (state, data) => {
  previousStatus(state, data);
  hardwareBusy = ["running","assigning","cleaning","releasing","offline"].includes(state)
    || Boolean(data.adapter_busy || data.selection_locked || breakerPending || startPending);
  $("ob-refresh").disabled = hardwareBusy;
  document.querySelectorAll(".hardware-profile-search").forEach((button) => {button.disabled = hardwareBusy;});
};
function plain(tag, value, className) {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  return element;
}
function loadHardware(data) {
  hardwareDevices = data.devices || [];
  const selected = $("ob-chip").value;
  $("ob-chip").replaceChildren(new Option("All chip families", ""));
  for (const chip of [...new Set(hardwareDevices.map((d) => d.chip).filter(Boolean))].sort()) $("ob-chip").append(new Option(chip,chip));
  if (hardwareDevices.some((d) => d.chip===selected)) $("ob-chip").value=selected;
  $("ob-meta").textContent = data.updated_at ? hardwareDevices.length + " community records · Last fetched "
    + new Date(data.updated_at).toLocaleString() + (data.version ? " · Dataset v"+data.version : "")
    : "No cached OpenBeken data. Update the database once; it then works offline.";
  hardwarePage=0; renderHardware();
}
async function showHardware(device) {
  try {
    const response = await fetch("api/cloudcutter/hardware/"+device.id);
    const detail = await response.json();
    if (!response.ok) throw new Error(detail.error || "Hardware record unavailable");
    $("ob-dialog-title").textContent = detail.name;
    $("ob-dialog-meta").textContent = [detail.vendor,detail.model,detail.chip,detail.board].filter(Boolean).join(" · ");
    $("ob-template-json").textContent = JSON.stringify(detail.template,null,2);
    $("ob-dialog").showModal();
  } catch (error) {notice(error.message,true);}
}
async function findHardwareProfiles(device) {
  if (hardwareBusy) return;
  if (!breakerDevices.length) await $("cc-refresh").onclick();
  $("cc-search").value = device.model || device.name;
  $("cc-search").oninput();
  $("hardware-explorer").open = false;
  $("cc-search").scrollIntoView({block:"center"});
  notice("Searching CloudCutter by model. Verify the exact device revision and original firmware; a hardware entry alone does not establish compatibility.");
}
function renderHardware() {
  const terms = $("ob-search").value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const chip = $("ob-chip").value;
  const matches = hardwareDevices.filter((device) => {
    const haystack = [device.name,device.vendor,device.model,device.chip,device.board,...device.keywords].join(" ").toLocaleLowerCase();
    return terms.every((term) => haystack.includes(term)) && (!chip || device.chip===chip)
      && (!$("ob-detailed").checked || device.detailed) && (!$("ob-template").checked || device.has_template);
  });
  const pages = Math.max(1,Math.ceil(matches.length/HARDWARE_PAGE_SIZE));
  hardwarePage = Math.min(hardwarePage,pages-1);
  $("ob-results").replaceChildren();
  for (const device of matches.slice(hardwarePage*HARDWARE_PAGE_SIZE,(hardwarePage+1)*HARDWARE_PAGE_SIZE)) {
    const tile = document.createElement("article"); tile.className="device-tile";
    const badges = document.createElement("div"); badges.className="device-badges";
    badges.append(plain("span",device.chip || "Chip unknown"),plain("span","Hardware reference","reference"));
    tile.append(badges,plain("h4",device.name),plain("p",[device.vendor,device.model,device.board].filter(Boolean).join(" · ")),
      plain("p",device.keywords.slice(0,8).join(" · "),"device-keywords"));
    const actions = document.createElement("div"); actions.className="device-tile-actions";
    const detail = plain("button",device.has_template ? "View pin-map reference" : "View hardware details","secondary");
    detail.type="button"; detail.onclick=()=>showHardware(device);
    const find = plain("button","Find CloudCutter profiles","secondary hardware-profile-search");
    find.type="button"; find.disabled=hardwareBusy; find.onclick=()=>findHardwareProfiles(device);
    actions.append(detail,find);
    if (device.guide_url) {
      const link = plain("a",device.detailed ? "Detailed teardown ↗" : "Community thread ↗","button secondary");
      link.href=device.guide_url; link.target="_blank"; link.rel="noopener noreferrer"; actions.append(link);
    }
    tile.append(actions); $("ob-results").append(tile);
  }
  if (!matches.length) $("ob-results").append(plain("p",hardwareDevices.length ? "No matching hardware records. Try another model, module or keyword." : "Load the OpenBeken database to explore community hardware records.","explorer-empty"));
  $("ob-count").textContent = matches.length + " matches / " + hardwareDevices.length + " records · Hardware data, not proof of an unpatched firmware";
  $("ob-page").textContent = "Page "+(hardwarePage+1)+" / "+pages;
  $("ob-previous").disabled=hardwarePage===0; $("ob-next").disabled=hardwarePage>=pages-1;
}
$("ob-refresh").onclick=async()=>{
  if (hardwareBusy) return;
  $("ob-refresh").textContent="Updating device database…";
  notice("Downloading the official OpenBeken hardware database; existing cached records remain available.");
  try {loadHardware(await breakerRequest("api/cloudcutter/hardware/refresh")); notice("OpenBeken hardware database updated. Thank you to OpenBeken and Elektroda's contributors.");}
  catch(error) {notice("Hardware update failed; any cached records remain usable. "+error.message,true);}
  finally {$("ob-refresh").textContent="Update OpenBeken database";}
};
$("ob-search").oninput=()=>{clearTimeout(hardwareTimer); hardwareTimer=setTimeout(()=>{hardwarePage=0;renderHardware();},150);};
for(const id of ["ob-chip","ob-detailed","ob-template"]) $(id).onchange=()=>{hardwarePage=0;renderHardware();};
$("ob-reset").onclick=()=>{$("ob-search").value="";$("ob-chip").value="";$("ob-detailed").checked=false;$("ob-template").checked=false;hardwarePage=0;renderHardware();};
$("ob-next").onclick=()=>{hardwarePage++;renderHardware();};
$("ob-previous").onclick=()=>{hardwarePage=Math.max(0,hardwarePage-1);renderHardware();};
$("ob-close").onclick=()=>$("ob-dialog").close();
$("ob-copy").onclick=async()=>{
  try {await navigator.clipboard.writeText($("ob-template-json").textContent);notice("Hardware reference JSON copied. It has not been applied to a device.");}
  catch(_){const range=document.createRange();range.selectNodeContents($("ob-template-json"));window.getSelection().removeAllRanges();window.getSelection().addRange(range);notice("Clipboard unavailable in Ingress; the reference text is selected for manual copying.");}
};
fetch("api/cloudcutter/hardware").then(async(response)=>{if(response.ok)loadHardware(await response.json());}).catch(()=>{});
renderHardware();
