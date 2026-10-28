"use strict";
// Render the Web UI against canned data to produce the screenshots in docs/images.
// Nothing runs on hardware: every request is answered by this script. Needs Playwright:
//   node tools/render_screenshots.cjs
const fs = require("node:fs");
const path = require("node:path");
const {chromium} = require("playwright");

const STATIC = "untuyaos3/app/static";
const PLACEHOLDERS = {
  CSRF: "demo", VERSION: "1.0.0", REPORT_URL: "https://example.invalid/", HELPER_URL: "https://example.invalid/",
  UPSTREAM_URL: "https://github.com/tuya-cloudcutter/UnTuyaOS3", UPSTREAM_REVISION: "2111458",
  UPSTREAM_COMMIT_URL: "https://github.com/tuya-cloudcutter/UnTuyaOS3", REPOSITORY_URL: "https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App"
};
const BASE = {state: "select_adapter", exit_code: null, adapter: null, events: [], cursor: 0, generation: "demo",
  selection_locked: false, adapter_busy: false, adapter_error: "", recovery_pending: "", selected_adapter: null,
  adapters: [], usb_devices: [], host: {kernel: "6.18.52-haos", loaded_wifi_modules: []}};
const READY = {...BASE, state: "ready", selected_adapter: "wlan1",
  helper: {state: "ready", version: "1.0.0", expected_version: "1.0.0", message: "Connected to the Wi-Fi Helper."},
  adapters: [{name: "wlan1", phy: "phy1", driver: "ath9k_htc", bus: "USB", eligible: true, reason: ""},
             {name: "wlp3s0", phy: "phy0", driver: "rtw88_8822ce", bus: "PCI/internal", eligible: false,
              reason: "wlp3s0: in use (administratively UP, has addresses, or part of bridge/bond)"}],
  usb_devices: [{path: "1-2", id: "0cf3:9271", product: "UB91", drivers: ["ath9k_htc"], interfaces: ["wlan1"], assigned_interface: null, hint: ""}],
  host: {kernel: "6.18.52-haos", loaded_wifi_modules: ["ath9k_htc", "ath9k_common", "rtw88_8822ce"]}};
const SCENES = {
  "webui-ready.png": READY,
  "webui-helper-missing.png": {...BASE, adapter_error: "Wi-Fi Helper unavailable. Start it first.",
    helper: {state: "unreachable", version: null, expected_version: "1.0.0",
             message: "The Wi-Fi Helper is not running. Start it from its app page; this page notices it automatically."}}
};

(async () => {
  const index = fs.readFileSync(path.join(STATIC, "index.html"), "utf8")
    .replace(/__([A-Z_]+)__/g, (match, name) => PLACEHOLDERS[name] ?? match);
  const browser = await chromium.launch();
  for (const [file, status] of Object.entries(SCENES)) {
    const page = await browser.newPage({viewport: {width: 1180, height: 760}});
    await page.route("http://demo.invalid/**", (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/") return route.fulfill({contentType: "text/html", body: index});
      if (url.pathname === "/api/events") return route.fulfill({contentType: "application/json", body: JSON.stringify(status)});
      if (url.pathname === "/api/firmware") return route.fulfill({contentType: "application/json", body: JSON.stringify({files: {T1: ["a.bin", "b.bin"], BK7231N: ["c.bin"], RTL8720CF: []}})});
      return route.fulfill({path: path.join(STATIC, url.pathname.slice(1))});
    });
    await page.goto("http://demo.invalid/");
    await page.waitForTimeout(600);
    await page.screenshot({path: path.join("docs/images", file), fullPage: false});
    await page.close();
    console.log("wrote docs/images/" + file);
  }
  await browser.close();
})();
