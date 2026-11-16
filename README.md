# NetBox Abhängigkeitsmodell

Mit diesem Projekt dokumentierst du in [NetBox](https://github.com/netbox-community/netbox) die Abhängigkeiten zwischen **Geschäftsprozessen, Applikationen, VMs, Clustern, Netzwerk und Stromversorgung**. Zwei Auswertungen bauen darauf auf: Welche Folgen hat ein Ausfall oder eine Wartung, und wovon hängt ein bestimmtes Objekt ab?

Gedacht ist es für den Betrieb, in dem diese Fragen regelmäßig auftauchen:

- **Updateplanung:** Was ist betroffen, wenn dieser Switch oder Host gewartet wird?
- **Notfallplanung (BCM):** Welche Prozesse fallen aus, und in welcher Reihenfolge erfolgt der Wiederanlauf?
- **NIS2 / ISMS:** Wie wirken sich Infrastrukturausfälle auf kritische Prozesse aus? Das Ergebnis ist nachvollziehbar und versioniert.
- **Backup-Planung:** Welche Systeme stehen hinter Prozessen mit RPO-Anforderungen?

Das Projekt kommt **ohne eigenes Plugin** aus. Es nutzt das offizielle Plugin [NetBox Custom Objects](https://github.com/netboxlabs/netbox-custom-objects) und NetBox Custom Scripts.

---

## Funktionsumfang

**Datenmodell** (Custom Object Types, versioniert als Portable Schema):

| Typ | Zweck |
|---|---|
| Geschäftsprozess | Prozess mit BIA-Kennzahlen (RTO, RPO, MTPD), Verantwortlichem und NIS2-Relevanz |
| Applikation | Fachanwendung oder IT-Dienst |
| Redundanzgruppe | „Mindestens N von M Mitgliedern müssen verfügbar sein“, z. B. ein Switch-Paar |
| Abhängigkeit | Gerichtete Kante „Quelle benötigt Ziel“ mit Typ und Kritikalität (hart / degradiert / keine) |

Die Datenbank erzwingt dabei zwei Regeln:
- Jede Abhängigkeit existiert nur einmal, eindeutig über Quelle, Ziel und Typ.
- Objekte, die in einer Abhängigkeit verwendet werden, lassen sich nicht löschen.

**Impact-Analyse** (Custom Script): Du wählst Objekte und ein Szenario (Ausfall oder Wartung). Das Script zeigt betroffene Prozesse, Applikationen und Systeme mit der Stufe AUSFALL oder DEGRADIERT und gibt das Ergebnis zusätzlich als CSV aus. Die Ausbreitung berücksichtigt:

- **Strom:** Unterverteilung → Stromkreis → Netzteil. Eine PDU zählt als Quelle.
- **Verkabelung:** Ein Gerät gilt als isoliert, wenn alle seine Gegenstellen ausgefallen sind.
- **Cluster-Quorum:** Mehrheit der Hosts, optional mit QDevice.
- **VMs:** Unterschieden wird zwischen HA-VMs und an einen Host gebundenen VMs.
- **Redundanzgruppen:** Die Stufe hängt von der geforderten Mindestanzahl aktiver Mitglieder ab.
- **Abhängigkeitskanten:** Die Kritikalität der Kante bestimmt, was weitergegeben wird.

Dazu kommen Prüfungen der Datenqualität: Zyklen, RTO > MTPD, unvollständige Kanten und zu kleine Cluster.

**Abhängigkeitsbaum** (Custom Script): Für ein beliebiges Objekt zeigt das Script mehrstufig, was es **benötigt** und wovon es **benötigt wird**. Optional kommen die direkten Kabelverbindungen hinzu.

---

## Voraussetzungen

- NetBox **≥ 4.7**
- `netboxlabs-netbox-custom-objects` **≥ 1.0.0**
- PostgreSQL, Redis und ein laufender RQ-Worker. Custom Scripts laufen über den Worker.
- Für das Setup: Python ≥ 3.10 mit `requests` und `pyyaml`

> **Hinweis zu NetBox 4.5.x:** Plugin 1.0.0 startet zwar unter NetBox 4.5.4, die Listenansichten brechen aber mit
> `BaseTable._apply_prefetching() takes 1 positional argument but 2 were given` ab. Unter 4.7 tritt der Fehler nicht auf.

---

## Installation

### 1. Plugin installieren

Siehe die [Installationsanleitung des Plugins](https://netboxlabs.com/docs/custom-objects/installation/).

### 2. Schema einspielen

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests pyyaml

export NETBOX_URL="https://netbox.example.org"
export NETBOX_AUTH="Token <api-token>"        # v2-Token: "Bearer nbt_<key>.<token>"
# export NETBOX_CA_BUNDLE=./ca.pem            # nur bei eigener oder selbstsignierter CA

python setup_abhaengigkeiten.py abhaengigkeiten_schema.yaml --preview-only   # Vorschau, ändert nichts
python setup_abhaengigkeiten.py abhaengigkeiten_schema.yaml                  # anwenden, nach Bestätigung
```

Das Script legt die benötigten Choice Sets an oder prüft sie, zeigt die Änderungen als Vorschau und wendet sie erst nach Bestätigung mit `ja` an. Destruktive Änderungen lehnt es grundsätzlich ab.

Der API-Token braucht dafür Schreibrechte auf Choice Sets und Custom Object Types. Nach dem Einspielen solltest du ihn widerrufen oder auf Leserechte beschränken.

### 3. Scripts installieren

`impact_analyse.py` lädst du unter *Customization → Scripts* hoch. Die Datei enthält beide Scripts.

### 4. Optional: Anzeige und Direktlinks

- **Anzeigeausdruck für Abhängigkeiten.** Unter *Custom Object Type „Abhängigkeit“ → Display expression* trägst du ein:
  ```
  {{ quelle }} → {{ ziel }}
  ```
  Diese Einstellung gehört nicht zum Portable-Schema-Format und muss deshalb von Hand gesetzt werden.
- **Custom Links „Abhängigkeiten“** je Objekttyp:
  ```
  /extras/scripts/<SCRIPT-ID>/?objekt=dcim/device:{{ object.pk }}
  /extras/scripts/<SCRIPT-ID>/?objekt=custom-objects/applikation:{{ object.pk }}
  ```

---

## Konventionen

1. **Bindung von VMs:** Ist bei einer VM ein Host eingetragen, ist sie an diesen gebunden (kein HA oder Hostfixierung). Ist nur der Cluster eingetragen, ist sie eine HA-VM. Davon hängt die Impact-Analyse ab.
2. **Redundanz** modellierst du ausschließlich über Redundanzgruppen. Die Scripts leiten sie nie aus der Verkabelung ab.
3. **Keine doppelten Kanten:** VM → Cluster, Host → Cluster, Kabel und Strom liest das Script aus den NetBox-Kernobjekten. Dafür legst du keine Abhängigkeiten an.
4. **Schemaänderungen** laufen nur über `abhaengigkeiten_schema.yaml`:
   - Feld-IDs bleiben dauerhaft gleich.
   - Entfernte Felder kommen nach `removed_fields`.
   - Die Version zählst du nach PEP 440 hoch.

### Beispiel

```
Geschäftsprozess "Abrechnung"
  └─ benötigt [hart] → Applikation "ERP"
        ├─ läuft auf [hart] → VM "erp01" ─→ Cluster ─→ Hosts ─→ Strom
        ├─ authentifiziert über [hart] → Applikation "Active Directory"
        │     └─ läuft auf [hart] → Redundanzgruppe "DCs" (min. 1 von 2)
        └─ benötigt [hart] → Redundanzgruppe "Access-Switche" (min. 1 von 2)
              └─ benötigt [hart] → Redundanzgruppe "Core-Switche" (min. 1 von 2)
```

---

## Grenzen

- **Konservativ:** Verliert ein Cluster das Quorum, gelten alle seine VMs als ausgefallen.
- **Keine Kapazitätsprüfung:** Ob die verbleibenden Hosts genug Ressourcen haben, prüfen die Scripts nicht.
- **Ceph** wird nicht eigens modelliert. Ein Storage-Netz bildest du über Redundanzgruppen und Abhängigkeiten ab.
- **Bei HA-VMs ist der aktuelle Host bewusst nicht dokumentiert.** Bei einem Hostausfall gibt die Analyse deshalb nur einen Sammelhinweis pro Cluster aus.
- **Die Ergebnisse sind nur so gut wie die Daten:** Fehlende Verkabelung, Netzteile oder Abhängigkeiten führen dazu, dass Auswirkungen nicht gemeldet werden.

---

## Entwicklung

Die Rechenkerne (`berechne_impact`, `baue_baum`) sind reine Funktionen und lassen sich ohne NetBox testen:

```bash
python3 -I tests/test_engine.py
```

Änderungen dokumentierst du in [`CHANGELOG.md`](CHANGELOG.md).

## Lizenz

[Apache License 2.0](LICENSE), dieselbe Lizenz wie NetBox selbst.

Das Plugin *NetBox Custom Objects* steht unter einer eigenen Lizenz (NetBox Limited Use License 1.0) und ist **nicht** Teil dieses Repositorys.
