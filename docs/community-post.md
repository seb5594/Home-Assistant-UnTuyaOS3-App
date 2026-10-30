# Announcement drafts

Texts for the Home Assistant community forum and for Reddit (r/homeassistant). Edit freely, add one or two screenshots from `docs/images/` and post. Both communities dislike pure self-promotion, so the post asks for feedback and test reports. Reddit: use the *Share Your Project* flair. Forum: *Share your Projects!*, tag it `app`.

---

## English

**Title:** Flash open firmware onto some Tuya devices from inside Home Assistant (UnTuyaOS3 as an app)

Hi everyone,

I buy far too many cheap smart gadgets, and a lot of them (LSC lamps and LED strips from Action, for example) only talk to the Tuya cloud. For some of them there is a way out: [UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3) from the tuya-cloudcutter people uses an exploit to put open firmware (ESPHome Kickstart) on the device over Wi-Fi, no screwdriver needed. The catch is that you need a Linux box, a suitable Wi-Fi adapter and a handful of scripts, and my Linux box is my Home Assistant.

So I put it **into** Home Assistant. It is two apps (a small helper and the main app) that work like this:

- You plug a spare USB Wi-Fi adapter into your HA machine and pick it in the web UI.
- The helper takes that one radio away from the host and gives it to the main app, which keeps it in an isolated network namespace. Your normal network is untouched, and everything is handed back when you are done.
- You put the device into pairing mode, press start and answer the script's numbered menu. Console, live logs, a firmware library and log download are all in the sidebar.

The part I'm happiest with is probably the stuff around it that you only notice when it goes wrong: it never flips an adapter that is in use, it recovers the radio even if the USB stick gets renumbered, it tells you in plain words why an adapter is rejected, and it separates "exploit accepted", "all bytes sent", "device confirmed" and "booted" because those are not the same thing.

**What has worked so far** (my own devices, one firmware version each):

- LSC Smart Floor Lamp (T1, firmware 1.2.1): flashed, the device confirmed the OTA. This was with an Atheros AR9271 USB stick (`ath9k_htc`).
- LSC Smart Connect table lamp (Action 3225458): Kickstart is running afterwards, but I have not configured the lamp's outputs yet.
- LSC Smart LED Strip Kit (Action 3225770, firmware 1.0.28): exploit accepted.
- A 2024 Battletron lightbar answered with something else, so the app stopped there. That is a useful result too.

**Please read this before you try it:** flashing can brick a device. A finished transfer does not guarantee that it boots, and I have no way to promise it works on your unit. Only use it on devices you can afford to lose. The exploit only affects some firmware versions, so the product name tells you very little.

**Firmware for the Action devices:** flashing Kickstart is just the first step. For devices sold by the discounter Action (LSC Smart, Battletron, Eurodomest) I built a [collection of prebuilt ESPHome firmware](https://gitea.seb5594.xyz/seb5594/Action_Battleton_Eurodomest_LSC-Smart-Custom-Firmware-Collection) that you can download from my Gitea and flash with the app.

**What I'd love your help with:** a compatibility list. I know three devices and one adapter; you know hundreds. There is a "Report a device" button in the app that opens a GitHub form with your adapter and versions already filled in. Failures help just as much as successes. If you try a Wi-Fi adapter other than the AR9271, I especially want to hear about it.

**Credits:** all the clever work (exploit, protocol, scripts, firmware) belongs to the [tuya-cloudcutter](https://github.com/tuya-cloudcutter) community, and the original exploit comes from kuba2k2 and the [LibreTiny](https://github.com/libretiny-eu/libretiny) project. I only wrapped it for Home Assistant, so please give them a star. The app links to the original project in its web UI, and a workflow watches their repository for new releases.

Repository, install steps and docs: https://github.com/seb5594/Home-Assistant-Anti-Tuya-Apps

It is free and MIT licensed, built in my spare time. Questions, bug reports and "it bricked my X" stories are all welcome.

---

## Deutsch (für das deutsche Forum)

**Titel:** Offene Firmware auf manche Tuya-Geräte flashen, direkt aus Home Assistant (UnTuyaOS3 als App)

Hallo zusammen,

ich kaufe viel zu viele günstige Smart-Home-Gadgets, und viele davon (zum Beispiel LSC-Lampen und LED-Streifen von Action) sprechen nur mit der Tuya-Cloud. Für einige gibt es einen Ausweg: [UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3) von den tuya-cloudcutter-Leuten nutzt einen Exploit, um per WLAN offene Firmware (ESPHome Kickstart) auf das Gerät zu bringen, ganz ohne Schraubenzieher. Der Haken: Man braucht einen Linux-Rechner, einen passenden WLAN-Adapter und ein paar Skripte, und mein Linux-Rechner ist mein Home Assistant.

Also habe ich es **in** Home Assistant gepackt. Es sind zwei Apps (ein kleiner Helper und die Haupt-App):

- Ein übriger USB-WLAN-Adapter wird in den HA-Rechner gesteckt und in der Web-Oberfläche ausgewählt.
- Der Helper nimmt dem Host genau dieses Funkmodul weg und gibt es der Haupt-App, die es in einem isolierten Netzwerk-Namespace hält. Dein normales Netzwerk bleibt unberührt, und danach wird alles zurückgegeben.
- Gerät in den Kopplungsmodus, Start drücken, das nummerierte Menü des Skripts beantworten. Konsole, Live-Logs, Firmware-Bibliothek und Log-Download sind in der Seitenleiste.

Am meisten freut mich vermutlich das Drumherum, das man erst merkt, wenn etwas schiefgeht: Ein Adapter, der gerade benutzt wird, wird nie angefasst. Das Funkmodul wird auch dann wiederhergestellt, wenn der USB-Stick neu durchnummeriert wird. Du bekommst in Klartext gesagt, warum ein Adapter abgelehnt wird. Und die App unterscheidet „Exploit akzeptiert“, „alle Bytes gesendet“, „Gerät hat bestätigt“ und „gebootet“, denn das ist nicht dasselbe.

**Was bisher geklappt hat** (meine eigenen Geräte, je eine Firmware-Version):

- LSC Smart Floor Lamp (T1, Firmware 1.2.1): geflasht, das Gerät hat das OTA bestätigt. Mit einem Atheros-AR9271-USB-Stick (`ath9k_htc`).
- LSC Smart Connect Tischlampe (Action 3225458): Danach läuft Kickstart, die Ausgänge der Lampe habe ich aber noch nicht eingerichtet.
- LSC Smart LED Strip Kit (Action 3225770, Firmware 1.0.28): Exploit akzeptiert.
- Eine Battletron-Lightbar von 2024 hat anders geantwortet, also hat die App dort angehalten. Auch das ist ein nützliches Ergebnis.

**Bitte vor dem Ausprobieren lesen:** Flashen kann ein Gerät unbrauchbar machen. Ein abgeschlossener Transfer garantiert nicht, dass es danach bootet, und ich kann nicht versprechen, dass es bei deinem Gerät klappt. Nimm nur Geräte, die du notfalls verschmerzen kannst. Der Exploit betrifft nur manche Firmware-Versionen, der Produktname sagt also wenig.

**Firmware für die Action-Geräte:** Kickstart ist nur der erste Schritt. Für Geräte vom Discounter Action (LSC Smart, Battletron, Eurodomest) habe ich eine [Sammlung vorgebauter ESPHome-Firmware](https://gitea.seb5594.xyz/seb5594/Action_Battleton_Eurodomest_LSC-Smart-Custom-Firmware-Collection) gebaut, die du von meinem Gitea laden und mit der App flashen kannst.

**Wobei ich eure Hilfe gebrauchen kann:** eine Kompatibilitätsliste. Ich kenne drei Geräte und einen Adapter, ihr kennt Hunderte. In der App gibt es einen Button „Report a device“, der ein GitHub-Formular mit eurem Adapter und den Versionen vorausgefüllt öffnet. Fehlschläge helfen genauso wie Erfolge. Wenn ihr einen anderen WLAN-Adapter als den AR9271 ausprobiert, will ich das ganz besonders wissen.

**Credits:** Die ganze clevere Arbeit (Exploit, Protokoll, Skripte, Firmware) gehört der [tuya-cloudcutter](https://github.com/tuya-cloudcutter)-Community, der ursprüngliche Exploit stammt von kuba2k2 und dem [LibreTiny](https://github.com/libretiny-eu/libretiny)-Projekt. Ich habe es nur für Home Assistant verpackt, gebt ihnen also gern einen Stern. Die App verlinkt das Originalprojekt in ihrer Oberfläche, und ein Workflow beobachtet deren Repository auf neue Releases.

Repository, Installation und Doku: https://github.com/seb5594/Home-Assistant-Anti-Tuya-Apps

Kostenlos, MIT-Lizenz, in der Freizeit gebaut. Fragen, Fehlerberichte und „hat mir mein X gebrickt“-Geschichten sind alle willkommen.
