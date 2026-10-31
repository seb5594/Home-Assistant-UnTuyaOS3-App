<h1 align="center">UnTuyaOS3 für Home Assistant</h1>

<p align="center">
  <img src="https://raw.githubusercontent.com/seb5594/Home-Assistant-UnTuyaOS3-App/main/untuyaos3/logo.png" alt="UnTuyaOS3" width="360" height="129">
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fseb5594%2FHome-Assistant-UnTuyaOS3-App"><img src="https://img.shields.io/static/v1?label=Home%20Assistant&amp;message=Repository%20hinzuf%C3%BCgen&amp;color=18BCF2&amp;logo=homeassistant&amp;logoColor=white&amp;style=for-the-badge" alt="Repository hinzufügen" height="28"></a>
  <a href="https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App/releases/latest"><img src="https://img.shields.io/github/v/release/seb5594/Home-Assistant-UnTuyaOS3-App?style=for-the-badge&amp;color=1877A5" alt="Version" height="28"></a>
</p>

---

[English](README.md) · **Deutsch**

> [!CAUTION]
> ## Flashen kann dein Gerät unbrauchbar machen. Du machst das auf eigenes Risiko.
>
> Eine fertig übertragene Firmware, ein gültiges Image oder eine freundliche Log-Zeile bedeuten **nicht**, dass das Gerät danach auch bootet. Ein abgebrochener Upload, das falsche Image oder eine Firmware-Version, für die der Exploit nicht passt, können ein totes Gerät hinterlassen, das nur noch mit Lötkolben und Serial-Adapter zu retten ist.
>
> - Flashe nur Geräte, die du notfalls verschmerzen kannst.
> - Lies vorher die [Kompatibilitätsliste](docs/compatibility.md) und die [FAQ](https://github.com/tuya-cloudcutter/UnTuyaOS3/wiki/FAQ) des Originalprojekts.
> - Halte Strom und Signal bis zum Schluss stabil. Zieh den Stecker nicht mitten im Upload.
> - Es gibt keine Gewährleistung (siehe MIT-Lizenz) und keine Garantie für einen erfolgreichen Flash oder für eine Wiederherstellung.
>
> Eine meiner eigenen Lampen war nach dem Flashen dunkel. Sie lief mit Kickstart, aber ich habe das nur gemerkt, weil ich nach ihrem WLAN gesucht habe. [Die ganze Geschichte](docs/table-lamp-3225458.md) (englisch) solltest du vor dem Start lesen.

## Was ist das?


Viele günstige Smart-Home-Geräte (zum Beispiel die LSC-Lampen, LED-Streifen und Steckdosenleisten von Action) sprechen nur mit der Tuya-Cloud. [UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3) kann auf **manche** davon per WLAN eine offene Firmware aufspielen, ohne das Gehäuse zu öffnen, sofern ihre Firmware vom Exploit betroffen ist.

Normalerweise brauchst du dafür einen Linux-Rechner, einen WLAN-Adapter und einen Stapel Skripte. Diese App packt alles in Home Assistant. Du wählst in der Web-Oberfläche einen übrigen WLAN-Adapter aus, drückst Start und beantwortest das nummerierte Menü des Skripts. Konsole, Live-Logs und eine Firmware-Bibliothek sind direkt in der Seitenleiste. Der Adapter wird dem Host nur für die Dauer der Sitzung weggenommen und danach zurückgegeben, dein Netzwerk bleibt, wie es war.

![Die Web-Oberfläche mit verbundenem Helper und gewähltem Adapter](docs/images/webui-ready.png)

Ich baue sowas in meiner Freizeit, weil ich meine Geräte gern cloudfrei habe. Auf meiner eigenen Hardware läuft das Ganze richtig gut, deshalb heißt es jetzt 1.0. Gemeint ist damit: *die Software ist fertig*, nicht: *dein Gerät funktioniert*.

> **Ehre, wem Ehre gebührt.** Der Exploit, die Protokollarbeit, die Skripte und die mitgelieferte Firmware stammen von der [tuya-cloudcutter](https://github.com/tuya-cloudcutter)-Community. UnTuyaOS3 ist deren Projekt, den ursprünglichen Exploit hat [kuba2k2](https://github.com/kuba2k2) von [LibreTiny](https://github.com/libretiny-eu/libretiny) gefunden. Ich habe es nur für Home Assistant verpackt: Web-Oberfläche, isolierte WLAN-Behandlung, Logs, Uploads. Ohne deren Arbeit gäbe es nichts davon. Gebt ihrem Repository bitte einen Stern.

## Was bisher geklappt hat

Das sind meine eigenen Geräte, jeweils mit einer Firmware-Version. Details und die WLAN-Adapter stehen in der [Kompatibilitätsliste](docs/compatibility.md).

| Gerät | Original-Firmware | Ergebnis |
| --- | --- | --- |
| LSC Smart Floor Lamp (T1) | 1.2.1 | **Hat funktioniert.** Im Log steht die OTA-Abschlussantwort des Geräts. |
| LSC Smart Connect Tischlampe (Action 3225458) | 1.0.43 | **Teilweise.** Kickstart läuft, aber die Ausgänge der Lampe sind noch nicht eingerichtet. |
| LSC Smart LED Strip Kit (Action 3225770) | 1.0.28 | **Exploit akzeptiert.** Was danach passierte, ist nicht dokumentiert. |
| Battletron Lightbar (2024) | unbekannt | **Nicht akzeptiert.** Das Gerät antwortete mit `0x0C`, die App hat vor der nächsten Stufe angehalten. |

Ein Flash besteht aus mehreren Stufen, die jede für sich scheitern können: Exploit akzeptiert, Übertragung komplett, Gerät bestätigt, neue Firmware bootet, Ausgänge funktionieren. Die Liste hält sie auseinander. Kickstart ist nur eine allgemeine Setup-Firmware und kennt die Pins deiner Lampe erst, wenn du sie konfigurierst.

## Fertige Firmware für Action-Geräte

Das Flashen ist nur die halbe Miete: Danach braucht das Gerät eine Firmware, die seine Pins kennt. Für Geräte vom Discounter Action (Marken LSC Smart, Battletron und Eurodomest) habe ich eine [Sammlung vorgebauter ESPHome-Firmware](https://gitea.seb5594.xyz/seb5594/Action_Battleton_Eurodomest_LSC-Smart-Custom-Firmware-Collection) zusammengestellt und auf meinem eigenen Gitea abgelegt. Lade dir dort das Image für dein Gerät herunter, lade es in der Firmware-Bibliothek der Web-Oberfläche als UG-Image hoch und flashe es. Gilt nur für Geräte von Action. Es gilt wie immer: Prüfe, ob Gerät und Firmware-Version passen, und rechne damit, das Gerät zu riskieren.

## Was du brauchst

- Home Assistant OS (oder Supervised) auf **amd64 oder aarch64**.
- Home Assistant per **Ethernet** angebunden. Der Adapter zum Flashen wird dem Host kurzzeitig weggenommen, also darf es nicht der sein, über den HA selbst läuft.
- Einen übrigen **WLAN-Adapter mit AP-Modus**. Ein USB-Stick ist am einfachsten. Ich nutze einen Atheros AR9271 (`0cf3:9271`).
- Das Gerät, das du flashen willst, in Reichweite, und Geduld.

### Welche WLAN-Adapter könnten gehen?

Die App kann nur nutzen, was der HAOS-Kernel mitbringt. Das sind die WLAN-Treiber, die HAOS für USB und SDIO baut (Stand 28. Oktober 2026, Kernel 6.18):

| Familie | Treiber |
| --- | --- |
| Atheros | `ath9k_htc`, `carl9170`, `ath6kl_usb`, `ath10k_usb` |
| MediaTek | `mt7601u`, `mt76x0u`, `mt76x2u`, `mt7663u`, `mt7921u` |
| Ralink | `rt2500usb`, `rt73usb`, `rt2800usb` |
| Realtek | `rtl8xxxu`, `rtl8192cu`, `rtw88_8822bu`, `rtw88_8822cu`, `rtw88_8723du` |
| Broadcom, Marvell | `brcmfmac` (USB), `mwifiex` (USB) |

Eingebautes PCIe-WLAN ist ebenfalls abgedeckt (Intel `iwlwifi`, Atheros, MediaTek, Realtek, ...). Aufgelistet heißt **nicht** getestet. Bisher hat nur der AR9271 etwas geflasht. Das interne Realtek RTL8822CE verbindet sich zwar, hatte aber oft zu wenig Signal. AP-Modus und die Übergabe in den Namespace hängen vom Treiber ab, die App prüft beides, bevor sie irgendetwas anfasst. Die vollständige Liste mit typischen Chips steht in [docs/wifi-compatibility.md](docs/wifi-compatibility.md) (englisch). Dein Adapter fehlt in der Testliste? Dann [melde ihn](#hilf-bei-der-kompatibilitätsliste).

## Installation

1. In Home Assistant **Einstellungen → Apps → App-Store** öffnen, dann **⋮ → Repositories** und `https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App` hinzufügen. (Ältere Versionen nennen das *Add-ons*.)
2. **Beide** Apps installieren: **UnTuyaOS3** und den separaten **[WiFi App Helper](https://github.com/seb5594/Home-Assistant-WiFi-Helper-App)** aus dem Hauptkatalog. Zwei Apps sind Absicht, [hier steht warum](docs/architecture.md#why-two-apps) (englisch).
3. Ein Kopplungsgeheimnis mit mindestens 32 Zeichen wählen und in den **Konfigurations**-Tabs beider Apps denselben Wert eintragen. Kein gutes zur Hand? Öffne zuerst die Web-Oberfläche der Haupt-App, drück auf **Generate pairing secret** und füge das Ergebnis in beide ein.
4. **Schutzmodus** und AppArmor angeschaltet lassen. Den Helper starten, im Log auf *Ready* warten, dann die Haupt-App starten und **Web-UI öffnen** drücken.

Die Oberfläche beginnt mit einer Karte *Wi-Fi Helper*, die dir sagt, was fehlt: Helper läuft nicht, Geheimnisse stimmen nicht überein, Versionen passen nicht. Sie bemerkt den Helper, sobald er startet, die Reihenfolge ist also nicht kritisch. Nach dem Einstecken eines USB-Adapters **Refresh adapters** drücken.

Beide Apps starten absichtlich nur manuell. Bitte keinen Watchdog einrichten, der sie mitten im Flashen neu startet. Aktualisiere beide Apps gemeinsam.

## Ein Gerät flashen

1. Das Gerät in den AP-Kopplungsmodus versetzen, meist erkennbar am langsamen Blinken.
2. In der Web-Oberfläche **Start interactive session** drücken.
3. Die nummerierten Fragen des Skripts (Plattform und Firmware) im Feld **Menu choice** beantworten.
4. Konsole und Aktivitätspanel beobachten. Ausführliches Logging ist an, du siehst jeden Frame.
5. Wenn es endet: Ergebnis lesen und das **Gerät testen**. Exit-Status 0 ist kein unabhängiger Beweis, dass die neue Firmware läuft.
6. Die Haupt-App stoppen, wenn du fertig bist. Der Helper stellt den Adapter wieder her und bleibt bereit.

Das Schließen des Browsers bricht die Sitzung nicht ab, beim Wiederkommen wird die letzte Ausgabe erneut angezeigt. **Stop session** unterbricht das Skript, und ein unterbrochener Upload kann ein Gerät unbrauchbar machen.

*Unconfirmed* heißt: Alle Bytes wurden gesendet, aber das Gerät hat nie „fertig“ gemeldet. Such nach einem Kickstart-WLAN, bevor du irgendetwas anderes probierst.

## Wenn etwas nicht klappt

- **Kein Adapter in der Liste.** Der Grund steht unter dem Dropdown. Typisch: verbunden, in Benutzung, blockiert oder kein AP-Modus.
- **USB-Stick am Bus, aber keine Schnittstelle.** Es fehlt der Host-Treiber oder dessen Firmware. Direkt am Rechner einstecken, *Refresh adapters* drücken, im Host-Log von Home Assistant nach `ath9k_htc` oder Firmware-Fehlern schauen. Die Apps können keine Treiber installieren.
- **Signal um −90 dBm oder schlechter.** Zu schwach, auch direkt neben der Lampe. Antenne prüfen, Kopplungsmodus neu starten oder einen anderen Adapter probieren.
- **Gerät antwortet `0x0C` statt `0x16`.** WLAN und DHCP sind in Ordnung, aber diese Firmware spricht nicht das erwartete Protokoll. Die App hält absichtlich an. Prüfe die Firmware-Version im [Kompatibilitäts-Wiki](https://github.com/tuya-cloudcutter/UnTuyaOS3/wiki/Device-Compatibility) des Originalprojekts.
- **Alles andere.** Lies den *Log*-Tab beider Apps und schau in [How it works](docs/how-it-works.md) (englisch).

## Hilf bei der Kompatibilitätsliste

Welche Geräte, Chips und Adapter funktionieren, weiß man nur, weil Leute es ausprobieren. Wenn du etwas geflasht hast (oder daran gescheitert bist), sag es mir. Der Button **Report a device** unten in der Web-Oberfläche öffnet ein Formular, in dem App-Version und Adapter schon eingetragen sind. Du kannst das [Formular auch direkt öffnen](https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App/issues/new?template=device-report.yml). Fehlschläge sind genauso nützlich wie Erfolge. Bitte lass Schlüssel, UUIDs und Geräte-IDs weg, das Issue ist öffentlich.

## Sicherheit in Kürze

Die Haupt-App mit Web-Oberfläche und den Upstream-Skripten läuft in einem isolierten Netzwerk-Namespace und sieht nur die eine Funkeinheit, die sie bekommen hat. Der Helper ist der einzige Teil im Host-Netzwerk. Er hat keinen Webserver und dient nur dazu, Funkeinheiten hinein- und herauszubewegen. Beide sprechen über einen lokalen Socket, nachdem sie bewiesen haben, dass sie dasselbe Geheimnis kennen. Nichts davon hat Zugriff auf deine Home-Assistant-Konfiguration, den Docker-Socket oder die Supervisor-API. Die Einzelheiten, auch was der Helper trotzdem kann, stehen in [docs/architecture.md](docs/architecture.md) (englisch). AppArmor bitte nicht deaktivieren.

## Am Original dranbleiben

Gepinnte Upstream-Revision: [`2111458`](https://github.com/tuya-cloudcutter/UnTuyaOS3/commit/2111458225c269ddddf5353bf09a1e8f1096d959), also das Release v1.0.1 des Originalprojekts. Ein Workflow prüft täglich, ob UnTuyaOS3 etwas Neueres veröffentlicht hat, und öffnet dann einen Pull Request gegen `dev`. Veröffentlicht wird erst, wenn ich den Diff gelesen und getestet habe.

## Mehr Dokumentation (englisch)

- [How it works](docs/how-it-works.md): Adapter-Prüfung, WLAN-Verbindung, Firmware-Bibliothek, Logs und Wiederherstellung
- [Architecture](docs/architecture.md): warum zwei Apps, Berechtigungen, Aufbau des Quellcodes
- [Wi-Fi adapters on HAOS](docs/wifi-compatibility.md): Treiber und was getestet wurde
- [Kompatibilitätsliste](docs/compatibility.md)
- [Vorfall Tischlampe](docs/table-lamp-3225458.md)
- [Contributing](CONTRIBUTING.md)

Kein offizielles Home-Assistant- oder Tuya-Produkt. Tuya ist eine Marke ihres Inhabers. Icon und Logo hier sind meine eigene Grafik, nur das Orange ist eine Verbeugung vor der Marke. Die Upstream-Software und -Firmware behalten ihre eigenen Lizenzen.

## Unterstützung

Alle meine Projekte entstehen in meiner Freizeit, aus Spaß an der Sache. Trotzdem stecken viel Zeit und Sorgfalt drin. Wenn dir meine Arbeit geholfen hat, freue ich mich über einen heißen Kaffee für die nächste schlaflose Nacht.

[![PayPal](https://img.shields.io/static/v1?label=Support&message=PayPal&color=0070BA&logo=paypal&logoColor=white&style=for-the-badge)](https://paypal.me/seb5594) [![Buy Me a Coffee](https://img.shields.io/static/v1?label=Support&message=Buy%20Me%20a%20Coffee&color=FFDD00&logo=buy-me-a-coffee&logoColor=black&style=for-the-badge)](https://buymeacoffee.com/seb5594)

## Lizenz

[MIT](LICENSE).

## Eigenständige Repositories und Rückkehr zu 1.0.0

Diese Repository enthält wieder ausschließlich **UnTuyaOS3**, aktuell Version **1.0.1**. Der allgemeine [WiFi App Helper](https://github.com/seb5594/Home-Assistant-WiFi-Helper-App) und [Tuya Breaker](https://github.com/seb5594/Home-Assistant-Tuya-Breaker-App) haben eigene Repositories und unabhängige Versionen. Beide Apps aus dem [Hauptkatalog](https://github.com/seb5594/Home-Assistant-Apps) installieren. Der Helper besitzt die neue Kennung `wifi_helper` und ein allgemein benanntes privates Socket-Verzeichnis.

Vor dem Umzug alle Sitzungen beenden und die erfolgreiche Adapter-Rückgabe im alten Helper prüfen. Die [deutsche Migrationsanleitung](https://github.com/seb5594/Home-Assistant-WiFi-Helper-App/blob/dev/README.de.md) beachten; alte Wiederherstellungsdaten nicht löschen, solange Recovery aussteht.

Home Assistant führt kein automatisches Downgrade von 1.2 Beta auf 1.0.1 durch. Konfiguration und private Firmware-Bibliothek mit der Backup-Oberfläche sichern und die eigenständige App bei Bedarf im App-Store neu installieren bzw. neu erstellen. Dasselbe private Kopplungsgeheimnis übernehmen. Keine Host-Befehle nötig. Der historische Git-Tag `v1.0.0` und dessen Release-Dateien bleiben erhalten; der aktuelle `dev`-Stand und der Katalog enthalten die neue Einzel-App-Struktur.
