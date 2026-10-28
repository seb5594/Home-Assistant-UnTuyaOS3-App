# Architecture

## Why two apps?

People ask, and I asked myself too: is the Wi-Fi helper really a separate app, or did I just split it for the sake of security theatre? The honest answer is that it is mostly about what Linux allows, and a bit about security.

**What the job needs.** UnTuyaOS3 has to talk to the device over Wi-Fi, and I do not want it anywhere near the Wi-Fi or Ethernet connection Home Assistant itself uses. So the app takes an idle radio out of the host and gets it into a network namespace of its own. Two things follow from how the kernel works:

1. Moving a radio between namespaces (`iw phy ... set netns`) is something only a process in the *host* network namespace with `NET_ADMIN` can do. A normal app cannot even see the host's radios.
2. The radio needs somewhere to go. A container in the usual bridged Supervisor network *is* such a place. If everything lived in one host-network app, there would be no second namespace to move the radio to. Creating one from inside the app would need `SYS_ADMIN`, which is far more power than `NET_ADMIN`.

So the helper is the only part that sits on the host network (plus the D-Bus connection to NetworkManager, which it needs to mark exactly one interface as unmanaged). It has no web server and no shell. The main app, with the web UI and the upstream scripts, runs in an ordinary isolated container and only ever sees the one radio it was given.

**What a merge would cost.** In a single host-network app the Ingress server would listen on every host interface, the upstream flashing code would run next to the host's own services, and the radio would stay in the host namespace. That works, but it is a weaker setup than the one I have. Going the `SYS_ADMIN` way instead trades one big privilege for another. Neither is something I want to ship for a tool that flashes other people's devices.

**What the split does not buy you.** Be clear about this: the helper still has `NET_ADMIN` on the host network, and Linux does not limit that capability to a single interface name. A compromised helper could mess with host networking. The split only shrinks the amount of code that holds those rights to a few hundred lines without any network listener.

**A bonus.** The isolated namespace is exactly what a future tool like tuya-cloudcutter would need as well. It runs its own DHCP, DNS and HTTP(S)/MQTT servers on well-known ports. Inside the app's own namespace they cannot collide with services on the host and they are not reachable from your LAN.

Two apps cost some convenience, which is why the main app does a lot to hide it: it finds the helper by itself as soon as it starts, tells you in plain words what is missing (not running, wrong secret, version mismatch) and links to the helper's page. See the helper card at the top of the Web UI.

## The two apps at a glance

| Access | UnTuyaOS3 (main app) | UnTuyaOS3 Wi-Fi Helper |
| --- | --- | --- |
| Network | Isolated container namespace | Host network, needed to hand over the radio |
| Capabilities | `NET_ADMIN`, `NET_RAW`, but only inside its own namespace | `NET_ADMIN` |
| Host D-Bus | no | NetworkManager queries and the per-device *managed* property |
| Web server | Ingress only, accepts the real Supervisor address only | none |
| Docker socket, host PID, Supervisor API | no | no |
| All hardware, all USB devices, kernel modules | no | no |
| Home Assistant `/config` | not mounted | not mounted |
| `/share` | only `untuyaos3-private/`, enforced by AppArmor | only `untuyaos3-private/`, enforced by AppArmor |

`config.yaml`, AppArmor profiles and a unit test (`tests/test_packaging.py`) pin this table down, so a permission cannot creep in unnoticed.

## How the apps trust each other

The apps talk over a Unix socket in `/share/untuyaos3-private/`. Namespace descriptors are passed with `SCM_RIGHTS`, which works only locally: a descriptor cannot travel over TCP or HTTP. Container names or DNS names are addresses, not credentials, so they play no role.

Before any descriptor is accepted, both sides prove they know the pairing secret with a nonce-based HMAC challenge. The secret never crosses the socket, and the protocol version and the requested scope are part of the proof. When the helper hands a radio over it refuses its own host namespace as the destination. When the radio comes back, the helper briefly sends a read-only descriptor of its namespace to the authenticated app, which passes it to a fixed `iw` command for the leased radio and closes it again. Nobody ever enters the host namespace, and neither `setns`, host PID nor `SYS_ADMIN` is involved.

A secret you choose yourself is the price of this. I did not want the helper to generate one and drop it into `/share`, because other apps that map `share` could read it. The Web UI has a button that creates a good random one for you.

The main app's web side is small on purpose: numeric menu choices only, Ingress requests only (`172.30.32.2`, forwarded headers do not count), a CSRF token for every change, output rendered as text. The DHCP hook configures only the selected interface and ignores DNS and default routes from the device. Global rfkill changes and upstream's own network-manager restore are switched off.

Network namespaces separate networking, not the whole kernel. A physical radio is not a VM boundary.

## Source layout

```
project.json            single source: version, base image, pins, options, texts
tools/sync_project.py   generates config.yaml, Dockerfile, translations, build_info.json
shared/                 code used by both apps (copied into each app by the tool above)
templates/              Dockerfile templates
untuyaos3/              main app: web UI, session runner, adapter handling
untuyaos3_wifi/         helper: broker that hands radios over
tests/                  unit tests (no hardware needed)
docs/                   you are here
assets/branding/        SVG sources of the icons and logos
```

Home Assistant builds every app from its own folder, which is why the generated files are committed and why the shared code is copied instead of imported. CI fails if a generated file is stale. Details are in [CONTRIBUTING.md](../CONTRIBUTING.md).

### Main app (`untuyaos3/app/`)

| Module | What it does |
| --- | --- |
| `server.py` | Ingress web server, CSRF, firmware upload, log download |
| `runner.py` | Runs the one fixed upstream command in a PTY with timeout and cleanup |
| `devices.py` | Adapter list, selection, helper state, lease handling |
| `lease.py` | Client of the helper: inventory, lease, return |
| `supplicant.py`, `association.py` | Private `wpa_supplicant` and the verified association |
| `dhcp.py`, `ota_target.py` | DHCP hook and the per-session OTA target record |
| `ota_progress.py` | Which bytes were really sent, to tell *finished* from *unconfirmed* |
| `request_body.py` | Bounded request bodies, including Ingress streaming |
| `links.py` | Links shown in the UI (upstream credit, helper app, report form) |
| `static/` | The Web UI |
| `integration/patch_upstream.py` | The reviewed patches to the upstream scripts |

### Helper (`untuyaos3_wifi/app/`)

| Module | What it does |
| --- | --- |
| `broker.py` | Serves inventory, lease and return requests; owns recovery |
| `inventory.py` | Read-only look at adapters, USB devices and loaded drivers |

### Shared (`shared/`)

`protocol.py` (handshake and messages), `wifi.py` (adapter checks and cleanup), `journal.py` (logging).

## Upstream patches

UnTuyaOS3 itself is used as it comes, with a short list of patches applied at image build time (`untuyaos3/integration/patch_upstream.py`). Every patch replaces one exact snippet, and the build fails when upstream changes it. A new upstream revision therefore never ends up patched "almost right". Moving the pinned revision means reading the upstream diff and repeating the privilege review, see [CONTRIBUTING.md](../CONTRIBUTING.md).

A scheduled workflow watches for new upstream releases and opens a pull request against `dev` when one appears. See `.github/workflows/upstream-release.yml`.

## Tuya Breaker: combined app on dev

The new experimental `tuya_breaker/` app embeds UnTuyaOS3 and classic CloudCutter in one Ingress UI. It reuses the original app modules through `tools/sync_project.py`, rather than maintaining a second copy by hand. Breaker-specific modules handle tool selection, the bounded profile API and the CloudCutter workflow. The original UnTuyaOS3 app stays available.

Both tools use Python 3.13 in separate virtual environments because their `sslpsk3` APIs differ. They share one runner/lease; tool changes are refused during assignment, execution, cleanup and return. No nested Docker, host network, Supervisor API or host D-Bus is added to the main container. The existing helper can serve either main app, one lease at a time.

CloudCutter's Docker/host launcher is never invoked. The embedded controller drives only the leased radio, uses the existing verified association/DHCP target, tests real AP startup before exploitation, and runs foreground hostapd/dnsmasq/MQTT processes in its own process group. HTTP/TLS binds only to the radio's AP IP; MQTT uses that IP plus loopback; DNS/DHCP binds the leased interface. A per-run nftables forward chain with drop policy blocks routing from that AP to the container uplink. Only Breaker's AppArmor profile additionally allows the standard low-port `net_bind_service` capability. Shared cleanup removes the filter and restores managed mode before returning the radio.

The controller uses fixed subprocess arguments and validated profile/image identifiers; it exposes no arbitrary shell hooks. Configuration secrets are omitted from API status and kept only for the attempt. Generated local device keys are retained privately for explicit download. See [Tuya Breaker's documentation](../tuya_breaker/DOCS.md) for current limits and evidence.
