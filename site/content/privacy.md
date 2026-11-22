---
title: "Privacy / Datenschutz"
description: "Datenschutzerklärung von metzler.systems, betrieben von einer Privatperson. Kein Tracking zu Analysezwecken, keine Cookies. Hosting: Infomaniak Public Cloud (Schweiz)."
sitemap:
  disable: true
---

*This page contains the legally relevant privacy declaration. As the operator is based in Germany, the binding version is German, even though the rest of this site is in English.*

Stand: 22. November 2026

## 1. Verantwortliche

Diese Website wird als rein private, nicht kommerzielle persönliche Website betrieben. Ein kommerzielles Angebot (insbesondere ein Rechtsgeschäft) wird hier nicht angebahnt, eine Impressumspflicht nach § 5 DDG besteht für rein private Websites daher nicht. Zur Transparenz:

Verantwortliche im Sinne der DSGVO: Mia Metzler
Kontakt: {{< email img="kontakt" >}} (als Bild, damit die Adresse nicht von Spam-Bots ausgelesen werden kann)

## 2. Allgemeines zur Datenverarbeitung

Diese Website wird statisch ausgeliefert, ergänzt um einen öffentlichen Status-Endpunkt (siehe letzter Punkt). Konkret bedeutet das:

- Keine Cookies, die Website setzt keine Cookies und verwendet keinen lokalen Speicher für Analysezwecke (der Sitzungsspeicher dient ausschließlich dem Lasttest-Auslöser, siehe nächster Punkt).
- Kein Tracking zu Analysezwecken, keine Analyse-Tools, keine Werbe- oder Social-Media-Plugins. Die einzige Ausnahme ist der Lasttest-Auslöser unter `/api/load/`, siehe nächster Punkt.
- Keine externen Ressourcen, CSS und JavaScript werden ausschließlich von dieser Domain geladen, insbesondere werden keine Schriftarten (z. B. Google Fonts) von Dritten nachgeladen.
- Referrer-Politik: Die Seite ist so konfiguriert, dass beim Klick auf externe Links (z. B. LinkedIn, GitHub, Bandcamp, Hackerspaces) keine Information über die zuletzt besuchte Seite übertragen wird (`no-referrer`). Die verlinkten Websites verarbeiten Ihre Daten ab dem Aufruf nach ihren eigenen Datenschutzbestimmungen.
- Öffentliche Status-Endpunkte: Unter `/api/metrics/` liefert die Website Live-Metrieken ihres eigenen Betriebs aus (`/state` als Snapshot, `/history` als Zeitverlauf, `/stream` als Live-Verbindung. Name und UID der Deployments und Pods, Phase und gegebenenfalls Fehlergrund sowie CPU- und Speicherverbrauch). Die Endpunkte sind ohne Authentifizierung erreichbar, es werden dabei keine personenbezogenen Daten der Besucher verarbeitet oder übertragen.
- Lasttest-Auslöser (`/api/load/`): Beim Besuch der Startseite kann die Seite einmalig pro Sitzung einen kurzen Lasttest gegen die eigene Website auslösen (öffentliche Demo, siehe `apps/load/` in diesem Repository). Dafür werden für etwa eine Sekunde technische Browser-Signale gesammelt (z. B. ob Plugins vorhanden sind, welcher WebGL-Renderer gemeldet wird, ob Mausbewegungen oder Klicks stattfanden und wie lange es bis zur ersten Eingabe dauerte) und als `POST /api/load/` gesendet. Zweck und Rechtsgrundlage ist ausschließlich die Unterscheidung echter menschlicher Besucher von automatisierten Bots (Art. 6 Abs. 1 lit. f DSGVO, berechtigtes Interesse an der Abwehr automatisierter Zugriffe und am Schutz der eigenen Infrastruktur). Die Signale werden serverseitig nur als Annotation an einem Kubernetes-Job abgelegt, der spätestens nach einer Stunde automatisch gelöscht wird (TTL). Es wird kein Fingerprint gebildet und die Signale werden nicht mit der IP-Adresse verknüpft gespeichert (die IP erscheint nur im allgemeinen Server-Log, siehe Abschnitt 3). Eine nachträgliche Korrelation über gemeinsame Zeitstempel von Server-Log und Job-Annotation ist technisch nicht ausgeschlossen, beide Daten werden jedoch nur kurzfristig vorgehalten. Der Aufruf selbst ist wie jeder Seitenaufruf im Server-Log erfasst. Zur Missbrauchsabwehr (Rate-Limit gegen wiederholtes Auslösen) speichert der Last-Service die IP-Adresse des Aufrufs zusätzlich kurzzeitig im Arbeitsspeicher des eigenen Pods (Verfall nach spätestens 10 Minuten, Rechtsgrundlage ebenfalls Art. 6 Abs. 1 lit. f DSGVO). Auch die öffentlichen Status-Endpunkte unter `/api/metrics/` werden pro IP-Adresse kurzzeitig gedrosselt, die IP wird dafür bis zu 60 Sekunden nur im Arbeitsspeicher des Ingress-Controllers vorgehalten (ebenfalls Art. 6 Abs. 1 lit. f DSGVO) und nicht protokolliert.

## 3. Hosting: Infomaniak Public Cloud (Schweiz)

Die Website wird als statische Seite von einem nginx-Container (Image wird aus diesem [Repository](https://github.com/miathedev/metzler.systems) gebaut, siehe [site/Dockerfile](https://github.com/miathedev/metzler.systems/blob/main/site/Dockerfile)) auf einem Kubernetes-Cluster der Infomaniak Public Cloud ausgeliefert. Betrieben wird der Cluster von der Infomaniak Network SA, Rue Eugène Marziano 25, 1227 Les Acacias (GE), Schweiz, Serverstandort: Schweiz (eigene Rechenzentren von Infomaniak in der Schweiz). Für die Schweiz liegt ein Angemessenheitsbeschluss der EU nach Art. 45 DSGVO vor, die Datenübermittlung dorthin ist daher zulässig. Infomaniak verarbeitet personenbezogene Daten (insbesondere die Server-Logfiles, siehe unten) als Auftragsverarbeiter nach Art. 28 DSGVO, Infomaniak stellt einen entsprechenden Auftragsverarbeitungsvertrag bereit (https://www.infomaniak.com/de/agb/datenschutzgesetz). Datenschutzhinweise von Infomaniak: https://www.infomaniak.com/de/agb/datenschutzrichtlinien

Betrieb der Website (GitOps): Das Container-Image wird per CI-Pipeline gebaut und in der [GitHub Container Registry](https://ghcr.io/miathedev/metzler.systems/website) (GHCR) veröffentlicht, der Cluster bezieht es von dort und wird von Flux deklarativ aus dem Git-Repository dieser Website deployed (siehe [flux/cluster/infomaniak/](https://github.com/miathedev/metzler.systems/tree/main/flux/cluster/infomaniak)). Das Image wird serverseitig durch den Cluster abgerufen, dabei fallen keine personenbezogenen Daten der Besucher an. TLS-Zertifikate stellt Let's Encrypt über cert-manager aus, als Ingress-Controller dient Traefik. Ebenfalls über diesen Cluster und Flux wird eine kleine Metrics-API betrieben (siehe `apps/metric/` und `charts/metric/` in diesem Repository), die den Status-Endpunkt aus Abschnitt 2 unter `/api/metrics/` bereitstellt und ausschließlich Metriken des Namespace `website` ausliefert. Dort läuft außerdem der Load-Service (`apps/load/` und `charts/load/`), der den Lasttest-Auslöser aus Abschnitt 2 unter `/api/load/` bereitstellt.

Server-Logfiles: Bei jedem Aufruf erhebt und speichert der Webserver (nginx) bzw. der Ingress (Traefik) automatisch:

- IP-Adresse des zugreifenden Geräts
- Datum und Uhrzeit des Zugriffs
- aufgerufene Ressource (URL) und übertragene Datenmenge
- Browsertyp/Betriebssystem (User-Agent)
- ggf. Referrer und Meldungscode

Die Protokolle fallen als Container-Logs an und werden vom Cluster bzw. der Plattform von Infomaniak verarbeitet, eine gesonderte, dauerhaft gespeicherte Log-Datei existiert nicht. Zweck: technisch fehlerfreier Betrieb, Sicherheit und Missbrauchserkennung. Rechtsgrundlage: Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse an einem sicheren, stabilen Betrieb). Speicherdauer: kurzfristig gemäß den Plattform-Standards von Infomaniak, eine darüber hinausgehende Speicherung durch die Verantwortliche erfolgt nicht.

Backups: Es existieren keine klassischen Server-Backups. Die Website ist jederzeit vollständig aus dem Git-Repository und dem Image in der GHCR reproduzierbar (GitOps), das Repository ist die maßgebliche Quelle: https://github.com/miathedev/metzler.systems.

## 4. Ihre Rechte

Sie haben das Recht auf:

- Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16), Löschung (Art. 17), Einschränkung der Verarbeitung (Art. 18), Datenübertragbarkeit (Art. 20) sowie Widerspruch gegen die Verarbeitung (Art. 21)
- Beschwerde bei einer Datenschutz-Aufsichtsbehörde (Art. 77 DSGVO). Zuständig ist der Landesbeauftragte für den Datenschutz und die Informationsfreiheit Baden-Württemberg, Lautenschlagerstraße 20, 70173 Stuttgart, https://www.baden-wuerttemberg.datenschutz.de/

Anfragen richten Sie bitte an {{< email img="kontakt" >}}.

## 5. Aktualität und Anpassung

Diese Erklärung wird bei Änderungen der Website oder der eingesetzten Dienste angepasst. Es gilt die jeweils aktuell veröffentlichte Fassung.
