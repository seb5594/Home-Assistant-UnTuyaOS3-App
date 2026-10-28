"use strict";
// Browser QA with canned API responses; no device or network access occurs.
const {chromium} = require("playwright");
const fs = require("node:fs"), path = require("node:path"), assert = require("node:assert/strict");
const root = "tuya_breaker/app/static";
const template = fs.readFileSync(root + "/index.html", "utf8").replace(/__[A-Z_]+__/g, "demo");
(async () => {
  const browser = await chromium.launch(process.env.PLAYWRIGHT_CHANNEL ? {channel: process.env.PLAYWRIGHT_CHANNEL} : {});
  try {
    for (const width of [360, 390, 1280]) {
      let state = "ready", tool = "untuyaos3", configured = false;
      const errors = [];
      const hardware = Array.from({length:7},(_,i)=>({id:String(i+1).padStart(20,"0"),
        name:i===0 ? 'Test table lamp' : i===5 ? 'Test lamp <img src=x onerror="alert(1)">' : 'Test device '+(i+1),
        vendor:"Test",model:"MODEL0"+(i+1),chip:i===6 ? "ESP32" : "BK7231N",board:"CB2S",
        keywords:["lamp","relay"],detailed:i%2===0,has_template:true,guide_url:"https://www.elektroda.com/rtvforum/topic1.html"}));
      const hardwareData={devices:hardware,updated_at:"2026-10-28T00:00:00+00:00",version:"0.1"};
      const page = await browser.newPage({viewport: {width, height: 844}});
      page.on("pageerror", (error) => errors.push(String(error)));
      const status = () => ({state, tool, engine_ready: tool === "untuyaos3" || configured,
        cloudcutter_review: configured ? {device: "Test lamp", profile: "1.0.0 - BK7231N", chip: "BK7231N", method: "flash", firmware: "sample-bk7231n.ug.bin"} : null,
        selected_adapter: "wlan1", selection_locked: ["running", "releasing"].includes(state), adapter_busy: false,
        recovery_pending: "", helper: {state: "ready", version: "1.1.0-beta.1", message: "Connected."},
        adapters: [{name: "wlan1", phy: "phy1", driver: "ath9k_htc", bus: "USB", eligible: true}],
        usb_devices: [], host: {}, events: [], cursor: 0, generation: "demo"});
      await page.route("http://breaker.invalid/**", async (route) => {
        const url = new URL(route.request().url());
        let response;
        if (url.pathname === "/") return route.fulfill({contentType: "text/html", body: template});
        if (url.pathname === "/api/events") response = status();
        if (url.pathname === "/api/firmware") response = {files: {T1: ["kickstart-t1.bin"], BK7231N: ["sample-bk7231n.ug.bin"], BK7231T: ["sample-bk7231t.ug.bin"], RTL8710BN: [], RTL8720CF: []}};
        if (url.pathname.startsWith("/api/cloudcutter/catalogue")) response = {devices: [{slug: "test-lamp-v1.0.0", manufacturer: "Test", name: "Lamp v1.0.0"}]};
        if (url.pathname === "/api/cloudcutter/device") response = {profiles: [{slug: "test-profile", name: "1.0.0 - BK7231N", firmware: {chip: "BK7231N", name: "Test", sdk: "test"}}]};
        if (url.pathname === "/api/cloudcutter/hardware" || url.pathname === "/api/cloudcutter/hardware/refresh") response=hardwareData;
        if (/^\/api\/cloudcutter\/hardware\/[0-9]{20}$/.test(url.pathname)) response={...hardware[0],template:{name:hardware[0].name,pins:{6:"Rel;1"}}};
        if (url.pathname === "/api/cloudcutter/configure") {configured = true; response = {ok: true};}
        if (url.pathname === "/api/tool") {tool = route.request().postDataJSON().tool; response = {ok: true};}
        if (url.pathname === "/api/start") {state = "running"; response = {ok: true};}
        if (response) return route.fulfill({contentType: "application/json", body: JSON.stringify(response)});
        return route.fulfill({path: path.join(root, url.pathname.slice(1))});
      });
      await page.goto("http://breaker.invalid/");
      await page.waitForFunction(() => document.getElementById("state").textContent === "ready");
      assert.equal(await page.locator("#start").isDisabled(), true);
      if (width === 390) fs.writeFileSync("docs/images/breaker-mobile-untuyaos3.png", await page.screenshot({fullPage: true}));
      await page.locator("#tool-cloudcutter").click();
      await page.locator("#cloudcutter-settings").waitFor({state: "visible"});
      await page.locator("#hardware-explorer summary").first().click();
      await page.locator("#ob-refresh").click();
      await page.waitForFunction(()=>document.querySelectorAll(".device-tile").length===6);
      assert.equal(await page.locator(".device-tile img").count(),0,"Untrusted device names render as text");
      await page.locator("#ob-next").click();
      assert.equal(await page.locator(".device-tile").count(),1);
      await page.locator("#ob-previous").click();
      await page.locator("#ob-search").fill("Test MODEL01");
      await page.waitForFunction(()=>document.querySelectorAll(".device-tile").length===1);
      await page.getByRole("button",{name:"View pin-map reference"}).click();
      assert.equal(await page.locator("#ob-dialog").evaluate((el)=>el.open),true);
      assert.match(await page.locator("#ob-template-json").textContent(),/Rel;1/);
      await page.locator("#ob-close").click();
      if(width===390) fs.writeFileSync("docs/images/breaker-mobile-hardware.png",await page.locator("#hardware-explorer").screenshot());
      await page.getByRole("button",{name:"Find CloudCutter profiles"}).click();
      assert.equal(await page.locator("#cc-profile").inputValue(),"","Hardware never approves an exploit profile");
      assert.equal(await page.locator("#start").isDisabled(),true);
      await page.locator("#cc-search").fill("");
      await page.locator("#cc-refresh").click();
      await page.locator("#cc-device").selectOption("test-lamp-v1.0.0");
      await page.locator("#cc-load").click();
      await page.locator("#cc-profile").selectOption("test-profile");
      await page.locator("#cc-firmware").selectOption("sample-bk7231n.ug.bin");
      await page.locator("#cc-save").click();
      await page.waitForFunction(() => document.getElementById("cc-review").textContent.startsWith("Reviewed:"));
      await page.locator("#risk-ack").check();
      await page.waitForFunction(() => !document.getElementById("start").disabled);
      assert.equal(await page.locator("#cc-configuration").evaluate((el) => el.open), false);
      await page.locator(".appearance-card summary").click();
      await page.locator("#accent-colour").evaluate((el) => {el.value="#000000"; el.dispatchEvent(new Event("input"));});
      assert.equal(await page.locator("#tool-cloudcutter").evaluate((el) => getComputedStyle(el).color), "rgb(255, 255, 255)");
      assert.equal(await page.evaluate(() => localStorage.getItem("tuya-breaker-accent-v1")), "#000000");
      await page.locator("#accent-reset").click();
      await page.locator(".appearance-card summary").click();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow, false, "No horizontal scrolling at " + width + "px");
      if (width === 390) {
        fs.writeFileSync("docs/images/breaker-mobile-cloudcutter.png", await page.screenshot({fullPage: true}));
      }
      await page.locator("#start").click();
      await page.waitForFunction(() => document.getElementById("state").textContent === "running");
      assert.equal(await page.locator("#tool-untuyaos3").isDisabled(), true);
      assert.equal(await page.locator("#cc-save").isDisabled(), true);
      assert.equal(await page.locator("#adapter-select").isDisabled(), true);
      state = "releasing";
      await page.waitForFunction(() => document.getElementById("state").textContent === "releasing");
      assert.equal(await page.locator("#start").isDisabled(), true);
      state = "unconfirmed"; configured = false;
      await page.waitForFunction(() => document.getElementById("state").textContent === "unconfirmed");
      assert.equal(await page.locator("#adapter-select").isDisabled(), false);
      assert.equal(await page.locator("#start").isDisabled(), true);
      assert.deepEqual(errors, []);
      console.log("PASS: " + width + "px — tool/profile review, consent, session/cleanup locks, no overflow or JS errors");
      await page.close();
    }
  } finally { await browser.close(); }
})().catch((error) => {console.error(error); process.exitCode = 1;});
