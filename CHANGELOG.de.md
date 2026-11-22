[English](CHANGELOG.md) | **Deutsch**

# Changelog

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [SemVer](https://semver.org/lang/de/).
Bis 1.x: Schema-Versionen je Custom Object Type nach PEP 440, Git-Tag `schema-<version>`.

## Offen

### Roadmap
1. Produktiv-NetBox auf 4.7 heben, als eigener Change mit Backup und Rückfallplan; danach Plugin 2.0 ausrollen.
2. Daten vervollständigen: Hosts mit Cluster-Zuordnung, Verkabelung, Strom (Unterverteilung → Stromkreis → Netzteil).
3. Pilotprozess vollständig modellieren.
4. **Hypervisor-Sync** (z. B. Proxmox) mit Zeitplan: nie destruktiv, Abweichungen nur melden; HA-Status übernehmen, `device` nur bei VMs ohne HA setzen.
5. **Backup-Abgleich:** Applikation mit RPO → VMs → Backup-Jobs; fehlende oder zu seltene Sicherungen als Befund.

Datenbefunde werden **nicht** im Repository geführt (sicherheitsrelevant).

---

## [2.0.0] – 2026-11-22
Aus dem Abhängigkeitsmodell wird das **NetBox-Plugin netbox-dependencies** (Repository umbenannt von netbox-abhaengigkeiten; alte Links leiten weiter).

### Neu
- Eigene Modelle Geschäftsprozess, Applikation, Redundanzgruppe (mit Mitgliedern), Abhängigkeit – mit Liste, Detail, Bearbeiten, Massenimport/-löschung, REST-API und Suche. Die Prüfung RTO ≤ MTPD erfolgt jetzt direkt beim Speichern.
- Impact-Analyse und Abhängigkeitsbaum als Plugin-Seiten statt Custom Scripts, mit CSV-Export; Bereich „Abhängigkeiten“ auf den Detailseiten von Geräten, VMs, Clustern, Leitungen, Unterverteilungen, Stromkreisen und Diensten.
- Berechtigungen: Die Analyse rechnet auf der gesamten Infrastruktur, zeigt aber nur Objekte, die der Benutzer sehen darf (nur deren Anzahl).
- Mehrsprachigkeit: Oberfläche englisch mit mitgelieferter deutscher Übersetzung, Sprache nach Benutzer, sonst Englisch.
- Management-Command `import_custom_objects` übernimmt die Daten aus 1.x (Trockenlauf ohne `--commit`, idempotent). In der Testinstanz geprüft: alle 23 Objekte übernommen; die Impact-Analyse liefert in 7 Vergleichsszenarien exakt dieselben 65 Ergebnisse wie das bisherige Script.

### Geändert
- **Breaking:** Abhängigkeit vom Plugin NetBox Custom Objects entfällt; Auswahlwerte sind englisch (`runs_on`, `requires`, `authenticates_via`, `data_from`, `power_cooling`; `hard`, `degraded`, `none`).
- **Breaking:** Schnittstelle für andere Plugins: `/plugins/dependencies/impact/?scenario=outage|maintenance&device=…&virtualmachine=…` statt Script `ImpactAnalyse` mit `szenario`/`devices`/`vms`.
- Rechenkern unverändert übernommen (alle 15 Szenario-Tests), nur Bezeichner und Texte englisch und übersetzbar.

### Entfernt
- `impact_analyse.py` (Custom Scripts), `setup_abhaengigkeiten.py`, `abhaengigkeiten_schema.yaml`, `tests/test_engine.py` (Tests laufen jetzt im Plugin).

### Sicherheit
- Security-Audit vor dem Release (Bericht lokal): Der Bereich auf Detailseiten zeigt keine Gegenseiten ohne Leseberechtigung; die API verrät nicht, ob nicht sichtbare Objekt-IDs existieren; CSV-Export gegen Formel-Injection geschützt.

---

## [1.0.6] – 2026-11-22
### Dokumentation
- **README:** Anbindung an das Plugin `netbox-patch-management`. Der Script-Name `ImpactAnalyse` und die Felder `szenario`, `devices`, `vms` sind jetzt eine Schnittstelle und dürfen nicht umbenannt werden.

## [1.0.5] – 2026-11-21
### Neu
- **README:** Custom Links „Impact-Analyse“ für Gerät, VM, Cluster, Unterverteilung, Stromkreis und Leitung (`?devices=`, `?vms=`, `?clusters=`, `?powerpanels=`, `?powerfeeds=`, `?circuits=` mit `{{ object.pk }}`). Das Objekt ist im Formular vorausgewählt.
### Geändert
- Vorbefüllung des Script-Formulars aus GET-Parametern in NetBox 4.7 verifiziert. Damit ist auch der offene Punkt zu den Custom Links „Abhängigkeiten“ erledigt.

## [1.0.4] – 2026-11-16
### Behoben
- **Impact-Analyse / Abhängigkeitsbaum:** Einseitig terminierte Leitungen (z. B. Internetanschluss ohne dokumentierte Provider-Seite) werden als Gegenstelle erkannt. NetBox liefert bei solchen unvollständigen Kabelpfaden keine `connected_endpoints`. Bisher galt eine Firewall deshalb schon beim Ausfall ihres einzigen LAN-Switches als isoliert, und eine ausgefallene Leitung wirkte sich nicht auf das angeschlossene Gerät aus. Jetzt zählt die Leitungs-Terminierung am Pfadende (`CablePath.path_objects`, auch über Patchpanels hinweg).
- Tests: Szenario 15 (Gegenstellen).

## [1.0.3] – 2026-11-16
### Behoben
- **Impact-Analyse:** Betroffene Prozesse und Applikationen mit Stufe AUSFALL werden als Warnung statt als Fehler protokolliert. Bisher setzte NetBox den Job-Status dadurch auf „failed“, obwohl die Analyse korrekt durchlief. `log_failure` bleibt echten Fehlern vorbehalten (kein Ausgangsobjekt, Custom Object Types nicht ladbar, Objekt nicht gefunden). Die Stufe steht weiterhin im Text und in der CSV.

## [1.0.2] – 2026-11-16
### Behoben
- **Abhängigkeitsbaum:** Fehlen das Plugin oder die Custom Object Types `abhaengigkeit`/`redundanzgruppe`, bricht das Script mit einer verständlichen Meldung ab statt mit `KeyError`/`ImportError` (gleiches Verhalten wie die Impact-Analyse).
- **Tests:** Irreführende Zwischenausgabe „alle 9 Szenarien OK“ heißt jetzt „Szenarien 1–9 OK“.

## [1.0.1] – 2026-11-16
### Veröffentlichung
- **Hinzugefügt:** Veröffentlichung als öffentliches GitHub-Repository, Release `v1.0.1`.
- **Geändert:** `.gitignore` schließt zusätzlich `CLAUDE.md` und `.DS_Store` aus.
- **Entfernt:** Verweis auf `CLAUDE.md` im `README.md` (Datei ist nicht Teil des Repositorys).

## [1.0.0] – 2026-11-08
### Dokumentation
- **Hinzugefügt:** Lizenz Apache-2.0 (`LICENSE`, SPDX-Header in den Python-Dateien).
- **Hinzugefügt:** `README.md` für die Veröffentlichung. Interne Befunde und Umgebungsdetails ausgelagert nach `INTERN.md` (nicht versioniert).


### Schema 1.1.0 (`abhaengigkeit`)
- **Hinzugefügt:** `custom-objects/redundanzgruppe` als Quelltyp. Damit sind Gruppe-zu-Gruppe-Abhängigkeiten wie DIST → CORE möglich.
- Status: in der Testinstanz eingespielt. Damit ist bestätigt, dass das Plugin das Erweitern von `related_object_types` bei einem bestehenden polymorphen Feld zulässt.

### Impact-Analyse / Abhängigkeitsbaum (`impact_analyse.py`)
- **Hinzugefügt:** Script **Abhängigkeitsbaum**. Es zeigt mehrstufig „benötigt“ und „wird benötigt von“, dazu direkte Verkabelung. Wiederholungen werden markiert, Endpunkte ab vier Stück zu einer Sammelzeile zusammengefasst, Objekte mit Unterbaum stehen zuerst.
- **Geändert:** Die VM-Logik folgt jetzt der Konvention „Host eingetragen = gebunden, nur Cluster = HA“. Der Tag `kein-ha` dient nur noch der Plausibilitätsprüfung. Für HA-VMs gibt es Hinweise pro Cluster (Neustart oder Live-Migration) statt einer Einzelbewertung pro VM.
- **Hinzugefügt:** Parameter „QDevice-Stimmen je Cluster“. Die erste Logzeile zeigt die Ausgangsobjekte.
- **Geändert:** Die CSV-Ausgabe nutzt lesbare Typnamen statt interner Modellnamen.
- **Hinzugefügt:** Impact-Analyse mit Ausbreitung über Strom, Kabel, Cluster-Quorum, VMs, Redundanzgruppen und Abhängigkeitskanten. Dazu Prüfungen der Datenqualität und CSV-Export.
- Tests: 14 Szenarien in `tests/test_engine.py`.
- In der Testinstanz verifiziert: Laden der Custom Objects, polymorphe Felder, Select-Werte, Lesen der Gruppenmitglieder, Kritikalität „degradiert“, gebundene VM bei Hostausfall, Isolation über Kabel.

### Plattform
- **Geändert:** Testinstanz von NetBox 4.5.4 auf **4.7** gehoben. Grund: Plugin 1.0.0 bricht unter 4.5.4 in den Listenansichten ab (`_apply_prefetching`).

### Schema 1.0.0 (alle Typen)
- **Hinzugefügt:** Typen `geschaeftsprozess`, `applikation`, `redundanzgruppe`, `abhaengigkeit`. Choice Sets `abhaengigkeit_typ` und `kritikalitaet`.
- **Hinzugefügt:** Ziele der Abhängigkeit sind Applikation, Redundanzgruppe, Geschäftsprozess, VM, Cluster, Device, Stromkreis, Unterverteilung, Service und Leitung.
- **Entfernt** vor dem ersten Anwenden: `error_message` an Unique-Constraints, weil das Plugin es dort nicht zulässt.
- Getestet: Erneutes Ausführen ändert nichts (`has_changes: false`), die Eindeutigkeit (Quelle, Ziel, Typ) greift, der Löschschutz greift für Quelle und Ziel.

### Setup (`setup_abhaengigkeiten.py`)
- **Hinzugefügt:** Choice Sets anlegen oder prüfen (nie überschreiben), Vorschau, Anwenden nach Bestätigung mit `ja`, destruktive Änderungen werden abgelehnt.
- **Korrigiert:** Die Vorschau erwartet das Dokument direkt als Body, das Anwenden erwartet es verpackt in `{"schema": …}`.
