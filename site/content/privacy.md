---
title: "Privacy / Datenschutz"
description: "Datenschutzerklärung von metzler.systems — betrieben von einer Privatperson. Kein Tracking, keine Cookies. Hosting: Infomaniak Public Cloud (Schweiz)."
sitemap:
  disable: true
---

*This page contains the legally relevant privacy declaration. As the operator is based in Germany, the binding version is German — even though the rest of this site is in English.*

Stand: 21. November 2026

## 1. Verantwortliche

Diese Website wird als rein private, nicht kommerzielle persönliche Website betrieben. Ein kommerzielles Angebot (insbesondere ein Rechtsgeschäft) wird hier nicht angebahnt; eine Impressumspflicht nach § 5 DDG besteht für rein private Websites daher nicht. Zur Transparenz:

Verantwortliche im Sinne der DSGVO: Mia Metzler
Kontakt: {{< email img="kontakt" >}} (als Bild, damit die Adresse nicht von Spam-Bots ausgelesen werden kann)

## 2. Allgemeines zur Datenverarbeitung

Diese Website ist vollständig statisch. Konkret bedeutet das:

- Keine Cookies — die Website setzt keine Cookies und verwendet keinen lokalen Speicher für Analysezwecke.
- Kein Tracking, keine Analyse-Tools, keine Werbe- oder Social-Media-Plugins.
- Keine externen Ressourcen — CSS und JavaScript werden ausschließlich von dieser Domain geladen; insbesondere werden keine Schriftarten (z. B. Google Fonts) von Dritten nachgeladen.
- Referrer-Politik: Die Seite ist so konfiguriert, dass beim Klick auf externe Links (z. B. LinkedIn, GitHub, Bandcamp, Hackerspaces) keine Information über die zuletzt besuchte Seite übertragen wird (`no-referrer`). Die verlinkten Websites verarbeiten Ihre Daten ab dem Aufruf nach ihren eigenen Datenschutzbestimmungen.

## 3. Hosting: Infomaniak Public Cloud (Schweiz)

Die Website wird als statische Seite von einem nginx-Container (Image wird aus diesem [Repository](https://github.com/miathedev/metzler.systems) gebaut, siehe [site/Dockerfile](https://github.com/miathedev/metzler.systems/blob/main/site/Dockerfile)) auf einem Kubernetes-Cluster der Infomaniak Public Cloud ausgeliefert. Betrieben wird der Cluster von der Infomaniak Network SA, Rue Eugène Marziano 25, 1227 Les Acacias (GE), Schweiz; Serverstandort: Schweiz (eigene Rechenzentren von Infomaniak in der Schweiz). Für die Schweiz liegt ein Angemessenheitsbeschluss der EU nach Art. 45 DSGVO vor, die Datenübermittlung dorthin ist daher zulässig. Infomaniak verarbeitet personenbezogene Daten (insbesondere die Server-Logfiles, siehe unten) als Auftragsverarbeiter nach Art. 28 DSGVO; Infomaniak stellt einen entsprechenden Auftragsverarbeitungsvertrag bereit (https://www.infomaniak.com/de/agb/datenschutzgesetz). Datenschutzhinweise von Infomaniak: https://www.infomaniak.com/de/agb/datenschutzrichtlinien

Betrieb der Website (GitOps): Das Container-Image wird per CI-Pipeline gebaut und in der [GitHub Container Registry](https://ghcr.io/miathedev/metzler.systems/website) (GHCR) veröffentlicht; der Cluster bezieht es von dort und wird von Flux deklarativ aus dem Git-Repository dieser Website deployed (siehe [flux/cluster/infomaniak/](https://github.com/miathedev/metzler.systems/tree/main/flux/cluster/infomaniak)). Das Image wird serverseitig durch den Cluster abgerufen — dabei fallen keine personenbezogenen Daten der Besucher an. TLS-Zertifikate stellt Let's Encrypt über cert-manager aus; als Ingress-Controller dient Traefik.

Server-Logfiles: Bei jedem Aufruf erhebt und speichert der Webserver (nginx) bzw. der Ingress (Traefik) automatisch:

- IP-Adresse des zugreifenden Geräts
- Datum und Uhrzeit des Zugriffs
- aufgerufene Ressource (URL) und übertragene Datenmenge
- Browsertyp/Betriebssystem (User-Agent)
- ggf. Referrer und Meldungscode

Die Protokolle fallen als Container-Logs an und werden vom Cluster bzw. der Plattform von Infomaniak verarbeitet; eine gesonderte, dauerhaft gespeicherte Log-Datei existiert nicht. Zweck: technisch fehlerfreier Betrieb, Sicherheit und Missbrauchserkennung. Rechtsgrundlage: Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse an einem sicheren, stabilen Betrieb). Speicherdauer: kurzfristig gemäß den Plattform-Standards von Infomaniak; eine darüber hinausgehende Speicherung durch die Verantwortliche erfolgt nicht.

Backups: Es existieren keine klassischen Server-Backups. Die Website ist jederzeit vollständig aus dem Git-Repository und dem Image in der GHCR reproduzierbar (GitOps) — das Repository ist die maßgebliche Quelle: https://github.com/miathedev/metzler.systems.

## 4. Ihre Rechte

Sie haben das Recht auf:

- Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16), Löschung (Art. 17), Einschränkung der Verarbeitung (Art. 18), Datenübertragbarkeit (Art. 20) sowie Widerspruch gegen die Verarbeitung (Art. 21)
- Beschwerde bei einer Datenschutz-Aufsichtsbehörde (Art. 77 DSGVO). Zuständig ist der Landesbeauftragte für den Datenschutz und die Informationsfreiheit Baden-Württemberg, Lautenschlagerstraße 20, 70173 Stuttgart, https://www.baden-wuerttemberg.datenschutz.de/

Anfragen richten Sie bitte an {{< email img="kontakt" >}}.

## 5. Aktualität und Anpassung

Diese Erklärung wird bei Änderungen der Website oder der eingesetzten Dienste angepasst. Es gilt die jeweils aktuell veröffentlichte Fassung.
