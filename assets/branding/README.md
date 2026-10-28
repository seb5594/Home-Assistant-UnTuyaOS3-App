# Branding

Icon and logo of both apps, drawn from scratch for this project (MIT, like the rest of the repository).
They are not Tuya's logo. The orange is a nod to the brand, the chip, the squared "t" and the
opened corner are our own. Tuya is a trademark of its owner; this project is not affiliated with it.

| Source | Output |
| --- | --- |
| `icon.svg`, `logo.svg` | `untuyaos3/icon.png`, `untuyaos3/logo.png` |
| `icon-helper.svg`, `logo-helper.svg` | `untuyaos3_wifi/icon.png`, `untuyaos3_wifi/logo.png` |
| `icon-breaker.svg`, `logo-breaker.svg` | `tuya_breaker/icon.png`, `tuya_breaker/logo.png` |

The wordmark is converted to outlines, so no font is needed. Export the PNGs with `node tools/render_branding.cjs`.

Tuya Breaker keeps the original dark rounded tile and orange/red radio-chip language, with a white lightning cut as its own mark. Its logo subtitle is **Powered by tuya-cloudcutter + seb5594**. The SVG includes outlined text and the PNGs can be exported separately with `--breaker-only`. Set `PLAYWRIGHT_CHANNEL=msedge` when using an installed Edge browser instead of bundled Chromium.
