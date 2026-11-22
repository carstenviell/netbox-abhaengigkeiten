[English](README.md) | **Deutsch**

# NetBox Dependencies

[NetBox](https://github.com/netbox-community/netbox)-Plugin, mit dem du die Abhängigkeiten zwischen
**Geschäftsprozessen, Applikationen, VMs, Clustern, Netzwerk und Stromversorgung** dokumentierst. Darauf bauen zwei
Auswertungen auf: *Was ist betroffen, wenn diese Objekte ausfallen oder gewartet werden?* und *Wovon hängt dieses
Objekt ab?*

Gedacht für den Betrieb, in dem diese Fragen regelmäßig auftauchen:

- **Patch- und Updateplanung:** Was ist betroffen, wenn dieser Switch oder Host gewartet wird?
- **Notfallplanung (BCM):** Welche Prozesse fallen aus, in welcher Reihenfolge erfolgt der Wiederanlauf?
- **NIS2 / ISMS:** Wie wirken sich Infrastrukturausfälle auf kritische Prozesse aus – nachvollziehbar und versioniert.
- **Backup-Planung:** Welche Systeme stehen hinter Prozessen mit RPO-Anforderungen?

## Funktionen

**Datenmodell**

| Objekt | Zweck |
|---|---|
| Geschäftsprozess | Prozess mit BIA-Kennzahlen (RTO, RPO, MTPD), Verantwortlichem und NIS2-Relevanz. Die RTO darf die MTPD nicht überschreiten. |
| Applikation | Fachanwendung oder IT-Dienst |
| Redundanzgruppe | „Mindestens N von M Mitgliedern müssen verfügbar sein“, z. B. ein Switch-Paar (Mitglieder: Geräte, VMs, Cluster, Leitungen) |
| Abhängigkeit | Gerichtete Kante „Quelle benötigt Ziel“ mit Typ (läuft auf, benötigt, authentifiziert über, Daten von, Strom/Klima) und Kritikalität (hart / degradiert / keine) |

- Jede Abhängigkeit gibt es nur einmal je Quelle, Ziel und Typ.
- Objekte, die in einer Abhängigkeit verwendet werden, lassen sich nicht löschen (zuerst die Abhängigkeit entfernen).
- Quellen und Ziele: Geräte, VMs, Cluster, Leitungen, Unterverteilungen, Stromkreise, Applikationsdienste,
  Geschäftsprozesse, Applikationen und Redundanzgruppen.

**Impact-Analyse** (*Abhängigkeiten → Impact-Analyse* oder der Button auf der Seite eines Geräts, einer VM, eines
Clusters …): Objekte und Szenario (Ausfall oder Wartung) wählen. Das Ergebnis zeigt die betroffenen Geschäftsprozesse,
Applikationen und weiteren Objekte mit der Stufe *Ausfall* oder *degradiert* und dem Grund, Hinweise zu HA-VMs
(Neustart / Live-Migration) und Befunde zur Datenqualität; mit CSV-Export. Die Ausbreitung berücksichtigt:

- **Strom:** Unterverteilung → Stromkreis → Netzteil; eine PDU zählt als Quelle.
- **Verkabelung:** Ein Gerät gilt als isoliert, wenn alle verkabelten Gegenstellen ausgefallen sind (auch über
  einseitig terminierte Leitungen).
- **Cluster-Quorum:** Mehrheit der Hosts, optional mit QDevice-Stimmen.
- **VMs:** Eine VM mit eingetragenem Host ist an diesen gebunden, eine VM nur mit Cluster ist eine HA-VM.
- **Redundanzgruppen:** Die Stufe hängt von der geforderten Mindestzahl aktiver Mitglieder ab.
- **Abhängigkeitskanten:** Die Kritikalität bestimmt, was weitergegeben wird.

**Abhängigkeitsbaum** (Button an jedem unterstützten Objekt): mehrstufig, was das Objekt *benötigt* und *von wem es
benötigt wird*, optional mit den direkten Kabelverbindungen.

**Detailseiten** von Geräten, VMs, Clustern, Leitungen, Unterverteilungen, Stromkreisen und Diensten zeigen einen
Bereich *Abhängigkeiten* mit den direkten Abhängigkeiten und Buttons für Baum, Impact-Analyse und „Abhängigkeit
hinzufügen“.

**Berechtigungen werden beachtet:** Die Analyse rechnet immer auf der gesamten Infrastruktur, Objekte ohne
Leseberechtigung werden aber nie angezeigt – nur ihre Anzahl.

## Voraussetzungen

- NetBox **4.7** oder neuer

## Installation

Das Plugin liegt nicht auf PyPI. Installiert wird aus dem GitHub-Release-Archiv – das funktioniert ohne `git`, auch im
netbox-docker-Image. `v2.0.0` ggf. durch das gewünschte [Release](https://github.com/carstenviell/netbox-dependencies/releases)
ersetzen.

**NetBox aus dem Quellcode (systemd):**

```bash
sudo /opt/netbox/venv/bin/pip install https://github.com/carstenviell/netbox-dependencies/archive/refs/tags/v2.0.0.tar.gz

# bleibt bei NetBox-Upgrades erhalten (upgrade.sh installiert local_requirements.txt neu)
echo "https://github.com/carstenviell/netbox-dependencies/archive/refs/tags/v2.0.0.tar.gz" | \
  sudo tee -a /opt/netbox/local_requirements.txt
```

**netbox-docker:** in `plugin_requirements.txt`

```text
https://github.com/carstenviell/netbox-dependencies/archive/refs/tags/v2.0.0.tar.gz
```

und in `Dockerfile-Plugins` (aus dem `netbox`, `netbox-worker` und `netbox-housekeeping` per `docker-compose.override.yml` gebaut werden):

```dockerfile
FROM netboxcommunity/netbox:v4.7
COPY ./plugin_requirements.txt /opt/netbox/
RUN /usr/local/bin/uv pip install -r /opt/netbox/plugin_requirements.txt
```

Plugin aktivieren in der `configuration.py` (Docker: `configuration/plugins.py`):

```python
PLUGINS = [
    # ...
    'netbox_dependencies',
]
```

Migrationen anwenden und neu starten:

```bash
cd /opt/netbox/netbox
sudo /opt/netbox/venv/bin/python manage.py migrate
sudo systemctl restart netbox netbox-rq
```

Docker: `docker compose build --no-cache && docker compose up -d` – die Migrationen laufen beim Start automatisch.

### Berechtigungen

| Aufgabe | Berechtigung |
|---|---|
| Impact-Analyse, Abhängigkeitsbaum, Bereich auf Detailseiten | `netbox_dependencies.view_dependency` |
| Modell ansehen / pflegen | `view` / `add` / `change` / `delete` auf Geschäftsprozess, Applikation, Redundanzgruppe (Mitglied), Abhängigkeit |

Ergebnisse enthalten nur Objekte, die der Benutzer sehen darf (Objektberechtigungen gelten).

### Upgrade

Neues Release-Archiv installieren (auch in `local_requirements.txt` bzw. `plugin_requirements.txt` anpassen), danach
`migrate` und Neustart (Docker: neu bauen).

### Umstieg von 1.x (Custom Objects + Custom Scripts)

Version 1.x war kein Plugin: Sie nutzte [NetBox Custom Objects](https://github.com/netboxlabs/netbox-custom-objects) und
zwei Custom Scripts. 2.0 bringt eigene Modelle mit; die Daten übernimmt ein Management-Command (ohne `--commit` nur
Trockenlauf, idempotent, die Custom Objects bleiben unverändert):

```bash
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py import_custom_objects            # Trockenlauf
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py import_custom_objects --commit   # übernehmen
```

Danach die alten Custom Scripts und Custom Links entfernen; die Custom Object Types löschen, sobald der Import geprüft
ist. Andere Plugins, die das alte Script verlinken, müssen die neue URL nutzen (siehe unten).

### Schnittstelle für andere Plugins

Die Impact-Analyse lässt sich vorbelegt öffnen:
`/plugins/dependencies/impact/?scenario=outage|maintenance&device=<id>&virtualmachine=<id>&cluster=<id>&powerpanel=<id>&powerfeed=<id>&circuit=<id>`
(Parameter dürfen sich wiederholen). [netbox-patch-management](https://github.com/carstenviell/netbox-patch-management)
nutzt das.

## Sprache

Die Oberfläche ist englisch, eine deutsche Übersetzung wird mitgeliefert. Angezeigt wird die Sprache, die der Benutzer
in NetBox gewählt hat (*Profil → Einstellungen → Sprache*); für Sprachen ohne Übersetzung erscheint Englisch.

## Konventionen

1. **Bindung von VMs:** Ist bei einer VM ein Host eingetragen, ist sie an diesen gebunden (kein HA oder
   Hostfixierung). Ist nur der Cluster eingetragen, ist sie eine HA-VM. Davon hängt die Impact-Analyse ab.
2. **Redundanz** wird ausschließlich über Redundanzgruppen modelliert – nie aus der Verkabelung geraten.
3. **Keine doppelten Kanten:** VM → Cluster, Host → Cluster, Verkabelung und Strom liest das Plugin aus den
   NetBox-Kernobjekten; dafür keine Abhängigkeiten anlegen.

```
Geschäftsprozess "Abrechnung"
  └─ benötigt [hart] → Applikation "ERP"
        ├─ läuft auf [hart] → VM "erp01" ─→ Cluster ─→ Hosts ─→ Strom
        ├─ authentifiziert über [hart] → Applikation "Active Directory"
        │     └─ läuft auf [hart] → Redundanzgruppe "DCs" (min. 1 von 2)
        └─ benötigt [hart] → Redundanzgruppe "Access-Switche" (min. 1 von 2)
              └─ benötigt [hart] → Redundanzgruppe "Core-Switche" (min. 1 von 2)
```

## Grenzen

- **Konservativ:** Verliert ein Cluster das Quorum, gelten alle seine VMs als ausgefallen.
- **Keine Kapazitätsprüfung:** Ob die verbleibenden Hosts genug Ressourcen haben, wird nicht geprüft.
- **Ceph** wird nicht eigens modelliert; ein Storage-Netz bildest du über Redundanzgruppen und Abhängigkeiten ab.
- **Bei HA-VMs ist der aktuelle Host bewusst nicht dokumentiert** – bei einem Hostausfall gibt die Analyse einen
  Hinweis pro Cluster aus.
- **Die Ergebnisse sind nur so gut wie die Daten:** Fehlende Verkabelung, Netzteile oder Abhängigkeiten führen dazu,
  dass Auswirkungen nicht gemeldet werden.

## Entwicklung

```bash
cd ~/dev/netbox/netbox-docker   # oder die eigene NetBox
python manage.py test netbox_dependencies --keepdb
```

Die Rechenkerne für Impact und Baum (`engine.py`) sind reine Funktionen; ihre Szenario-Tests brauchen keine Datenbank.

## Lizenz

[Apache License 2.0](LICENSE), dieselbe Lizenz wie NetBox.
