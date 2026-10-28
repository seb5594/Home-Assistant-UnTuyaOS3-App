"use strict";
// Export the PNG pictures Home Assistant expects from the SVG sources in assets/branding.
// Needs Playwright with Chromium (npm i playwright). Run from the repository root:
//   node tools/render_branding.cjs
const fs = require("node:fs");
const path = require("node:path");
const {chromium} = require("playwright");

const JOBS = [
  ["icon.svg", "untuyaos3/icon.png", 256, 256],
  ["logo.svg", "untuyaos3/logo.png", 560, 200],
  ["icon-helper.svg", "untuyaos3_wifi/icon.png", 256, 256],
  ["logo-helper.svg", "untuyaos3_wifi/logo.png", 560, 200],
  ["icon-breaker.svg", "tuya_breaker/icon.png", 256, 256],
  ["logo-breaker.svg", "tuya_breaker/logo.png", 560, 200],
];

(async () => {
  const browser = await chromium.launch(process.env.PLAYWRIGHT_CHANNEL ? {channel: process.env.PLAYWRIGHT_CHANNEL} : {});
  for (const [source, target, width, height] of JOBS) {
    if (process.argv.includes("--breaker-only") && !source.includes("breaker")) continue;
    const svg = fs.readFileSync(path.join("assets/branding", source), "utf8")
      .replace("<svg ", `<svg width="${width}" height="${height}" `);
    const page = await browser.newPage({viewport: {width, height}});
    await page.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`);
    fs.writeFileSync(target, await page.screenshot({omitBackground: true}));
    await page.close();
    console.log(`${source} -> ${target} (${width}x${height})`);
  }
  await browser.close();
})();
