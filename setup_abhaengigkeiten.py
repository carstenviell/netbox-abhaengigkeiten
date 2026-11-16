#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Spielt das Abhängigkeitsmodell (Custom Objects) in NetBox ein.

Ablauf:
  1. Choice Sets anlegen bzw. prüfen (abhaengigkeit_typ, kritikalitaet)
  2. Schema-Preview -> Diff anzeigen, ohne etwas zu ändern
  3. Nach Bestätigung: Schema anwenden (nie destruktiv)

Aufruf:
  export NETBOX_URL="https://netbox.example.local"
  export NETBOX_AUTH="Token <key>"        # v1-Token
  # oder: export NETBOX_AUTH="Bearer nbt_<key>.<token>"   # v2-Token
  python3 setup_abhaengigkeiten.py abhaengigkeiten_schema.yaml [--preview-only]

Optional: NETBOX_CA_BUNDLE=/pfad/zur/ca.pem für eine interne CA.
Benötigt: requests, pyyaml
"""
import json
import os
import sys

import requests
import yaml

CHOICE_SETS = {
    "abhaengigkeit_typ": [
        ["laeuft_auf", "läuft auf"],
        ["benoetigt", "benötigt"],
        ["authentifiziert_ueber", "authentifiziert über"],
        ["daten_von", "Daten von"],
        ["strom_klima", "Strom/Klima"],
    ],
    "kritikalitaet": [
        ["hart", "hart (Ausfall)"],
        ["degradiert", "degradiert (eingeschränkt)"],
        ["keine", "keine"],
    ],
}


def session():
    url = os.environ.get("NETBOX_URL", "").rstrip("/")
    auth = os.environ.get("NETBOX_AUTH", "")
    if not url or not auth:
        sys.exit("NETBOX_URL und NETBOX_AUTH müssen gesetzt sein.")
    s = requests.Session()
    s.headers.update({
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    s.verify = os.environ.get("NETBOX_CA_BUNDLE", True)
    return s, url


def fail(resp, step):
    print(f"\nFEHLER bei {step}: HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(resp.text[:2000])
    sys.exit(1)


def ensure_choice_sets(s, url):
    ep = f"{url}/api/extras/custom-field-choice-sets/"
    for name, choices in CHOICE_SETS.items():
        r = s.get(ep, params={"name": name})
        if r.status_code != 200:
            fail(r, f"Abfrage Choice Set {name}")
        results = r.json()["results"]
        if results:
            existing = [list(c) for c in results[0].get("extra_choices") or []]
            if existing != choices:
                print(f"WARNUNG: Choice Set '{name}' existiert mit abweichenden "
                      f"Werten. Bitte manuell prüfen, es wird nicht überschrieben.\n"
                      f"  vorhanden: {existing}\n  erwartet:  {choices}")
            else:
                print(f"OK: Choice Set '{name}' vorhanden.")
            continue
        r = s.post(ep, json={"name": name, "extra_choices": choices})
        if r.status_code not in (200, 201):
            fail(r, f"Anlage Choice Set {name}")
        print(f"ANGELEGT: Choice Set '{name}'.")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    preview_only = "--preview-only" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    with open(args[0], encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    s, url = session()
    ensure_choice_sets(s, url)

    base = f"{url}/api/plugins/custom-objects/schema"
    # Preview erwartet das Schema-Dokument direkt als Body (verifiziert).
    r = s.post(f"{base}/preview/", json=doc)
    if r.status_code != 200:
        fail(r, "Preview")
    print("\n=== PREVIEW (es wurde nichts geändert) ===")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

    if preview_only:
        return
    if input("\nSchema jetzt anwenden? (ja/nein): ").strip().lower() != "ja":
        print("Abgebrochen.")
        return

    # Apply erwartet – anders als Preview – das Dokument in {"schema": ...}
    # verpackt (verifiziert). Destruktive Änderungen bleiben verboten.
    r = s.post(f"{base}/apply/",
               json={"schema": doc, "allow_destructive": False})
    if r.status_code == 409:
        fail(r, "Apply (destruktive Änderung erkannt, absichtlich abgelehnt)")
    if r.status_code not in (200, 201):
        fail(r, "Apply")
    print("\n=== ANGEWENDET ===")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
