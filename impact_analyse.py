# SPDX-License-Identifier: Apache-2.0
"""
NetBox Custom Script: Impact-Analyse über das Abhängigkeitsmodell

Beantwortet: "Was ist betroffen, wenn diese Objekte ausfallen bzw. gewartet werden?"
Schreibt NICHTS in die Datenbank (rein lesend).

Ausbreitungsregeln
  Strom      Unterverteilung -> Stromkreis -> Gerät (Gerät fällt aus, wenn ALLE
             angeschlossenen Netzteile keine Quelle mehr haben; PDU zählt als Quelle)
  Kabel      Gerät gilt als isoliert (Ausfall), wenn ALLE verkabelten Gegenstellen
             ausgefallen sind. Teilweise betroffene Geräte erscheinen nur als Hinweis
             (Redundanz wird über Redundanzgruppen modelliert, nicht geraten).
  Cluster    Ausfall, wenn weniger als die Mehrheit der Hosts verfügbar ist (Quorum).
  VMs        Konvention: Ist bei der VM ein Host (Device) eingetragen, ist sie an
             diesen gebunden (kein HA oder Hostfixierung) und fällt mit ihm aus.
             Ist nur der Cluster eingetragen, ist sie eine HA-VM und hängt nur am
             Cluster. Fällt ein Host aus, gibt das Script dazu einen Hinweis aus
             (Ausfall: HA-Neustart / Wartung: Live-Migration), weil der aktuelle
             Host einer HA-VM bewusst nicht dokumentiert ist.
  Gruppen    Redundanzgruppe: Ausfall bei < min_aktiv verfügbaren Mitgliedern,
             degradiert, sobald ein Mitglied fehlt.
  Kanten     Abhängigkeit (quelle -> ziel):
               Kritikalität "hart"       -> Quelle erbt den Zustand des Ziels
               Kritikalität "degradiert" -> Quelle wird höchstens degradiert
               Kritikalität "keine"      -> keine Wirkung

Voraussetzungen: NetBox >= 4.7, netbox-custom-objects >= 1.0.0, Schema
abhaengigkeiten_schema.yaml 1.0.0.
"""
from collections import defaultdict

AUSFALL = 2
DEGRADIERT = 1
STUFE_TEXT = {AUSFALL: "AUSFALL", DEGRADIERT: "DEGRADIERT"}


# ---------------------------------------------------------------------------
# Rechenkern – ohne NetBox-Abhängigkeiten, damit separat testbar
# ---------------------------------------------------------------------------
def berechne_impact(seeds, names, feed_panel, device_power, device_links,
                    cluster_hosts, vms, groups, edges, szenario="ausfall",
                    qdevice_stimmen=0):
    """
    Alle Objekte werden über Schlüssel (hashbar) referenziert.
      seeds         [key]                         Ausgangsobjekte
      names         {key: str}                    Anzeigenamen
      feed_panel    {feed_key: panel_key}
      device_power  {dev_key: [[quelle_key, ...] je angeschlossenem Netzteil]}
      device_links  {dev_key: [gegenstelle_key je verkabeltem Interface]}
      cluster_hosts {cluster_key: [dev_key]}
      vms           [(vm_key, cluster_key|None, dev_key|None, gebunden: bool)]
      groups        [(grp_key, [member_key], min_aktiv)]
      edges         [(quelle_key, ziel_key, kritikalitaet)]
    Rückgabe: (zustand {key: stufe}, grund {key: str}, hinweise [str])
    """
    zustand, grund = {}, {}
    migrationen = []

    def n(k):
        return names.get(k, str(k))

    def stufe(k):
        return zustand.get(k, 0)

    def markiere(k, s, warum):
        if k is None or stufe(k) >= s:
            return False
        zustand[k] = s
        grund[k] = warum
        return True

    for k in seeds:
        markiere(k, AUSFALL, "Ausgangsobjekt")

    for _ in range(1000):  # Fixpunkt-Iteration; Zustände steigen nur monoton
        geaendert = False

        # Strom: Unterverteilung -> Stromkreis
        for feed, panel in feed_panel.items():
            if panel is not None and stufe(panel) == AUSFALL:
                geaendert |= markiere(feed, AUSFALL,
                                      f"Unterverteilung {n(panel)} ausgefallen")

        # Strom: Gerät ohne versorgtes Netzteil
        for dev, ports in device_power.items():
            ports = [p for p in ports if p]
            if ports and all(all(stufe(q) == AUSFALL for q in p) for p in ports):
                geaendert |= markiere(dev, AUSFALL,
                                      "keine Stromversorgung mehr (alle Netzteile)")

        # Kabel: alle Gegenstellen weg -> isoliert
        for dev, peers in device_links.items():
            peers = [p for p in peers if p is not None]
            if peers and all(stufe(p) == AUSFALL for p in peers):
                geaendert |= markiere(dev, AUSFALL,
                                      "isoliert: alle verkabelten Gegenstellen ausgefallen")

        # Cluster-Quorum
        for cl, hosts in cluster_hosts.items():
            if not hosts:
                continue
            # QDevice-Stimmen gelten als verfügbar
            stimmen = len(hosts) + qdevice_stimmen
            verfuegbar = sum(1 for h in hosts if stufe(h) != AUSFALL) + qdevice_stimmen
            noetig = stimmen // 2 + 1
            if verfuegbar < noetig:
                geaendert |= markiere(cl, AUSFALL,
                                      f"Quorum verloren ({verfuegbar} von {stimmen} "
                                      f"Stimmen, nötig {noetig})")

        # VMs: mit Host-Eintrag = an den Host gebunden (kein HA / Hostfixierung),
        #       ohne Host-Eintrag = HA, hängt nur am Cluster
        for vm, cl, dev, gebunden in vms:
            if cl is not None and stufe(cl) == AUSFALL:
                geaendert |= markiere(vm, AUSFALL, f"Cluster {n(cl)} ausgefallen")
            elif dev is not None and gebunden and stufe(dev) == AUSFALL:
                geaendert |= markiere(vm, AUSFALL,
                                      f"an Host {n(dev)} gebunden (kein HA/Hostfixierung)")

        # Redundanzgruppen
        for grp, members, min_aktiv in groups:
            if not members:
                continue
            verfuegbar = sum(1 for m in members if stufe(m) != AUSFALL)
            if verfuegbar < (min_aktiv or 1):
                geaendert |= markiere(grp, AUSFALL,
                                      f"nur {verfuegbar} von {len(members)} verfügbar, "
                                      f"mindestens {min_aktiv} nötig")
            elif verfuegbar < len(members):
                geaendert |= markiere(grp, DEGRADIERT,
                                      f"Redundanz reduziert ({verfuegbar} von "
                                      f"{len(members)} verfügbar)")

        # Abhängigkeitskanten
        for quelle, ziel, krit in edges:
            s = stufe(ziel)
            if not s or krit == "keine":
                continue
            ziel_stufe = s if krit == "hart" else DEGRADIERT
            geaendert |= markiere(quelle, ziel_stufe,
                                  f"benötigt {n(ziel)} ({STUFE_TEXT[s].lower()})")

        if not geaendert:
            break

    # Hinweise zu HA-VMs: deren aktueller Host ist bewusst nicht dokumentiert
    for cl, hosts in cluster_hosts.items():
        weg = [h for h in hosts if stufe(h) == AUSFALL]
        if not weg or stufe(cl) == AUSFALL:
            continue
        ha_vms = [vm for vm, c, dev, gebunden in vms
                  if c == cl and stufe(vm) != AUSFALL and not (dev is not None and gebunden)]
        if not ha_vms:
            continue
        hosts_txt = ", ".join(n(h) for h in weg)
        if szenario == "ausfall":
            migrationen.append(
                f"Cluster {n(cl)}: Ausfall von {hosts_txt} – HA-VMs, die dort liefen, "
                f"werden neu gestartet (kurze Unterbrechung). Betroffen sein können bis zu "
                f"{len(ha_vms)} HA-VMs; welche genau, ist in NetBox nicht dokumentiert.")
        else:
            migrationen.append(
                f"Cluster {n(cl)}: Vor Wartung von {hosts_txt} HA-VMs per Live-Migration "
                f"verschieben ({len(ha_vms)} HA-VMs im Cluster). Kapazität der verbleibenden "
                f"{len(hosts) - len(weg)} Host(s) prüfen.")

    return zustand, grund, migrationen


def finde_zyklen(edges):
    """Stark zusammenhängende Komponenten (Tarjan) mit Zyklus."""
    graph = defaultdict(list)
    for q, z, _ in edges:
        graph[q].append(z)
    index, low, stack, on_stack, ergebnis = {}, {}, [], set(), []
    zaehler = [0]

    def besuche(v):
        index[v] = low[v] = zaehler[0]
        zaehler[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph[v]:
            if w not in index:
                besuche(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            komp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                komp.append(w)
                if w == v:
                    break
            if len(komp) > 1 or v in graph[v]:
                ergebnis.append(komp)

    for v in list(graph):
        if v not in index:
            besuche(v)
    return ergebnis


# ---------------------------------------------------------------------------
# NetBox-Anbindung
# ---------------------------------------------------------------------------
try:
    from extras.scripts import (Script, MultiObjectVar, ChoiceVar, StringVar,
                                 IntegerVar, BooleanVar)
    from dcim.models import Device, Interface, PowerFeed, PowerPanel, PowerPort
    from virtualization.models import Cluster, VirtualMachine
    from circuits.models import Circuit
    _IN_NETBOX = True
except ImportError:  # lokaler Test ohne NetBox
    _IN_NETBOX = False


def _key(obj):
    return (obj._meta.label_lower, obj.pk) if obj is not None else None


if _IN_NETBOX:

    class ImpactAnalyse(Script):

        class Meta:
            name = "Impact-Analyse"
            description = ("Zeigt, welche Systeme, Applikationen und Geschäftsprozesse "
                           "von Ausfall oder Wartung der gewählten Objekte betroffen sind.")
            commit_default = False

        szenario = ChoiceVar(
            choices=(("ausfall", "Ungeplanter Ausfall"),
                     ("wartung", "Geplante Wartung (HA-VMs werden migriert)")),
            default="ausfall", label="Szenario")
        devices = MultiObjectVar(model=Device, required=False, label="Geräte")
        vms = MultiObjectVar(model=VirtualMachine, required=False, label="VMs")
        clusters = MultiObjectVar(model=Cluster, required=False, label="Cluster")
        powerpanels = MultiObjectVar(model=PowerPanel, required=False,
                                     label="Unterverteilungen")
        powerfeeds = MultiObjectVar(model=PowerFeed, required=False, label="Stromkreise")
        circuits = MultiObjectVar(model=Circuit, required=False, label="Leitungen")
        tag_kein_ha = StringVar(default="kein-ha", required=False,
                                label="Tag-Slug für VMs ohne HA (nur Plausibilitätsprüfung)")
        qdevice = IntegerVar(default=0, min_value=0, required=False,
                             label="QDevice-Stimmen je Cluster",
                             description="0 = kein QDevice (Standard bei 3+ Hosts)")

        # --------------------------------------------------------------
        def run(self, data, commit):
            names, objs = {}, {}

            def reg(obj):
                if obj is None:
                    return None
                k = _key(obj)
                if k not in objs:
                    objs[k] = obj
                    names[k] = str(obj)
                return k

            seeds = [reg(o) for feld in ("devices", "vms", "clusters", "powerpanels",
                                         "powerfeeds", "circuits")
                     for o in (data.get(feld) or [])]
            if not seeds:
                self.log_failure("Bitte mindestens ein Ausgangsobjekt wählen.")
                return

            # Custom Objects
            try:
                from netbox_custom_objects.models import CustomObjectType

                def cot(name):
                    return CustomObjectType.objects.get(name=name).get_model_with_serializer()

                Abh, Grp, Proz, App = (cot("abhaengigkeit"), cot("redundanzgruppe"),
                                       cot("geschaeftsprozess"), cot("applikation"))
            except Exception as exc:
                self.log_failure(f"Custom Object Types nicht ladbar: {exc}")
                return
            proz_label = Proz._meta.label_lower
            app_label = App._meta.label_lower

            # Strom
            feed_panel = {reg(f): reg(f.power_panel)
                          for f in PowerFeed.objects.select_related("power_panel")}
            device_power = defaultdict(list)
            for pp in PowerPort.objects.filter(cable__isnull=False).select_related("device"):
                quellen = []
                for ep in pp.connected_endpoints or []:
                    if isinstance(ep, PowerFeed):
                        quellen.append(reg(ep))
                    elif getattr(ep, "device", None) is not None:  # PDU-Steckdose
                        quellen.append(reg(ep.device))
                device_power[reg(pp.device)].append(quellen)

            # Kabel
            device_links = defaultdict(list)
            for itf in Interface.objects.filter(cable__isnull=False).select_related("device"):
                for ep in itf.connected_endpoints or []:
                    if getattr(ep, "device", None) is not None:
                        device_links[reg(itf.device)].append(reg(ep.device))
                    elif getattr(ep, "circuit", None) is not None:
                        device_links[reg(itf.device)].append(reg(ep.circuit))

            # Cluster und VMs
            cluster_hosts = defaultdict(list)
            for d in Device.objects.filter(cluster__isnull=False).select_related("cluster"):
                cluster_hosts[reg(d.cluster)].append(reg(d))
            tag = (data.get("tag_kein_ha") or "").strip()
            vms = []
            for vm in VirtualMachine.objects.select_related(
                    "cluster", "device").prefetch_related("tags"):
                ohne_ha = bool(tag) and any(t.slug == tag for t in vm.tags.all())
                if ohne_ha and vm.device is None:
                    self.log_warning(f"Datenqualität: VM {vm} hat Tag '{tag}', aber keinen "
                                     f"Host eingetragen – Bindung unbekannt.", obj=vm)
                vms.append((reg(vm), reg(vm.cluster), reg(vm.device), vm.device is not None))

            # Redundanzgruppen und Kanten
            groups = []
            for g in Grp.objects.all():
                try:
                    members = [reg(m) for m in g.mitglieder.all()]
                except Exception as exc:
                    self.log_warning(f"Mitglieder von {g} nicht lesbar: {exc}", obj=g)
                    members = []
                groups.append((reg(g), members, g.min_aktiv or 1))
            edges, defekt = [], 0
            for e in Abh.objects.all():
                if e.quelle is None or e.ziel is None:
                    defekt += 1
                    continue
                edges.append((reg(e.quelle), reg(e.ziel), e.kritikalitaet or "hart"))

            # Rechnen
            zustand, grund, migrationen = berechne_impact(
                seeds, names, feed_panel, dict(device_power), dict(device_links),
                dict(cluster_hosts), vms, groups, edges, data.get("szenario", "ausfall"),
                data.get("qdevice") or 0)

            self.log_info("Ausgangsobjekte (" + data.get("szenario", "ausfall") + "): "
                          + ", ".join(names[k] for k in seeds))

            # Ausgabe
            self._ausgabe(zustand, grund, migrationen, objs, names,
                          proz_label, app_label, set(seeds))
            self._datenqualitaet(Proz, edges, defekt, cluster_hosts, vms, names, objs,
                                 data.get("qdevice") or 0)

            # CSV im Output-Tab
            zeilen = ["stufe;typ;objekt;grund"]
            for k, s in sorted(zustand.items(), key=lambda kv: (-kv[1], kv[0][0], names[kv[0]])):
                typ = str(objs[k]._meta.verbose_name) if k in objs else k[0]
                zeilen.append(f"{STUFE_TEXT[s]};{typ};{names[k]};{grund[k]}")
            return "\n".join(zeilen)

        # --------------------------------------------------------------
        def _ausgabe(self, zustand, grund, migrationen, objs, names,
                     proz_label, app_label, seeds):
            def gruppe(pred):
                return sorted((k for k in zustand if pred(k)),
                              key=lambda k: (-zustand[k], names[k]))

            prozesse = gruppe(lambda k: k[0] == proz_label)
            apps = gruppe(lambda k: k[0] == app_label)
            rest = gruppe(lambda k: k[0] not in (proz_label, app_label) and k not in seeds)

            if not prozesse:
                self.log_success("Kein Geschäftsprozess betroffen.")
            for k in prozesse:
                o = objs[k]
                rto = getattr(o, "rto_h", None)
                zusatz = f" | RTO {rto} h" if rto is not None else ""
                nis2 = " | NIS2" if getattr(o, "nis2_relevant", False) else ""
                text = f"PROZESS {STUFE_TEXT[zustand[k]]}: {names[k]}{zusatz}{nis2} – {grund[k]}"
                (self.log_failure if zustand[k] == AUSFALL else self.log_warning)(text, obj=o)

            for k in apps:
                text = f"Applikation {STUFE_TEXT[zustand[k]]}: {names[k]} – {grund[k]}"
                (self.log_failure if zustand[k] == AUSFALL else self.log_warning)(text, obj=objs[k])

            for k in rest:
                self.log_info(f"{STUFE_TEXT[zustand[k]]}: {names[k]} – {grund[k]}", obj=objs[k])

            for text in migrationen:
                self.log_warning(text)

        # --------------------------------------------------------------
        def _datenqualitaet(self, Proz, edges, defekt, cluster_hosts, vms, names, objs,
                            qdevice=0):
            if defekt:
                self.log_warning(f"Datenqualität: {defekt} Abhängigkeit(en) ohne Quelle/Ziel.")
            for komp in finde_zyklen(edges):
                self.log_warning("Datenqualität: Zyklus in Abhängigkeiten: "
                                 + " → ".join(names[k] for k in komp))
            for p in Proz.objects.all():
                if p.rto_h is not None and p.mtpd_h is not None and p.rto_h > p.mtpd_h:
                    self.log_warning(f"Datenqualität: RTO ({p.rto_h} h) > MTPD "
                                     f"({p.mtpd_h} h)", obj=p)
            for cl, hosts in cluster_hosts.items():
                if len(hosts) < 3 and not qdevice:
                    self.log_warning(f"Hinweis: Cluster {names[cl]} hat nur {len(hosts)} "
                                     f"Host(s) in NetBox und kein QDevice – ein Hostausfall "
                                     f"bedeutet Quorumverlust. Fehlen Hosts in NetBox?",
                                     obj=objs[cl])
            for vm, cl, dev, gebunden in vms:
                if cl is None and dev is None:
                    self.log_warning(f"Datenqualität: VM {names[vm]} ohne Cluster und Host.",
                                     obj=objs[vm])


# ===========================================================================
# Abhängigkeitsbaum: mehrstufige Ansicht "benötigt" / "wird benötigt von"
# ===========================================================================
TYP_LABEL = {"laeuft_auf": "läuft auf", "benoetigt": "benötigt",
             "authentifiziert_ueber": "authentifiziert über", "daten_von": "Daten von",
             "strom_klima": "Strom/Klima"}


def baue_baum(start, adj, max_tiefe=4):
    """
    adj: {key: [(nachbar_key, label)]}
    Rückgabe: [(tiefe, key, label, hinweis)]  hinweis: "" | "Zyklus" | "siehe oben" | "…"
    Jeder Knoten wird nur einmal aufgeklappt; Wiederholungen werden markiert.
    """
    zeilen, aufgeklappt = [], {start}

    def rek(k, tiefe, pfad):
        nachbarn = adj.get(k, [])
        # Endpunkte (ohne eigene Nachbarn) mit gleichem Label ab 4 Stück zusammenfassen
        blaetter = defaultdict(list)
        for nb, label in nachbarn:
            if not adj.get(nb) and nb not in pfad and nb not in aufgeklappt:
                blaetter[label].append(nb)
        sammeln = {label for label, liste in blaetter.items() if len(liste) > 3}
        gesammelt = set()
        # Knoten mit Unterbaum zuerst, Sammelzeilen danach
        nachbarn = sorted(nachbarn, key=lambda x: 0 if adj.get(x[0]) else 1)
        for nb, label in nachbarn:
            if label in sammeln and nb in blaetter[label]:
                if label not in gesammelt:
                    gesammelt.add(label)
                    zeilen.append((tiefe, tuple(blaetter[label]), label, "Sammelzeile"))
                    aufgeklappt.update(blaetter[label])
                continue
            if nb in pfad:
                zeilen.append((tiefe, nb, label, "Zyklus"))
            elif nb in aufgeklappt:
                zeilen.append((tiefe, nb, label, "siehe oben"))
            elif tiefe >= max_tiefe and adj.get(nb):
                zeilen.append((tiefe, nb, label, "…"))
            else:
                zeilen.append((tiefe, nb, label, ""))
                aufgeklappt.add(nb)
                rek(nb, tiefe + 1, pfad | {nb})

    rek(start, 1, {start})
    return zeilen


def umkehren(adj):
    rueck = defaultdict(list)
    for a, nachbarn in adj.items():
        for b, label in nachbarn:
            rueck[b].append((a, label))
    return dict(rueck)


if _IN_NETBOX:

    class Abhaengigkeitsbaum(Script):

        class Meta:
            name = "Abhängigkeitsbaum"
            description = ("Zeigt mehrstufig, wovon ein Objekt abhängt und was von ihm "
                           "abhängt (inkl. Redundanzgruppen, Cluster, VMs, Strom).")
            commit_default = False

        objekt = StringVar(label="Objekt",
                           description="Format typ:id, z. B. dcim/device:12 oder "
                                       "custom-objects/applikation:3 (per Custom Link)")
        tiefe = IntegerVar(default=4, min_value=1, max_value=10, label="Maximale Tiefe")
        verkabelung = BooleanVar(default=True, label="Direkte Kabelverbindungen zeigen")

        def run(self, data, commit):
            from django.apps import apps
            try:
                from netbox_custom_objects.models import CustomObjectType
                Abh, Grp = (CustomObjectType.objects.get(name=n).get_model_with_serializer()
                            for n in ("abhaengigkeit", "redundanzgruppe"))
            except Exception as exc:
                self.log_failure(f"Custom Object Types nicht ladbar: {exc}")
                return

            # --- Startobjekt auflösen ---
            roh = (data.get("objekt") or "").strip()
            try:
                typ, pk = roh.rsplit(":", 1)
                app, modell = typ.split("/", 1)
                if app == "custom-objects":
                    Model = CustomObjectType.objects.get(slug=modell).get_model_with_serializer()
                else:
                    Model = apps.get_model(app, modell)
                start_obj = Model.objects.get(pk=int(pk))
            except Exception as exc:
                self.log_failure(f"Objekt '{roh}' nicht gefunden: {exc}")
                return

            names, objs = {}, {}

            def reg(obj):
                if obj is None:
                    return None
                k = _key(obj)
                if k not in objs:
                    objs[k], names[k] = obj, str(obj)
                return k

            # --- Graph "X benötigt Y" aufbauen ---
            hoch = defaultdict(list)

            def kante(a, b, label):
                if a is not None and b is not None:
                    hoch[a].append((b, label))

            for e in Abh.objects.all():
                if e.quelle is None or e.ziel is None:
                    continue
                t = TYP_LABEL.get(e.typ, e.typ or "?")
                kante(reg(e.quelle), reg(e.ziel), f"{t} [{e.kritikalitaet or '?'}]")
            for g in Grp.objects.all():
                gk = reg(g)
                try:
                    for m in g.mitglieder.all():
                        kante(gk, reg(m), f"Mitglied (min. {g.min_aktiv} aktiv)")
                except Exception as exc:
                    self.log_warning(f"Mitglieder von {g} nicht lesbar: {exc}", obj=g)
            for vm in VirtualMachine.objects.select_related("cluster", "device"):
                vk = reg(vm)
                if vm.cluster:
                    kante(vk, reg(vm.cluster), "läuft im Cluster")
                if vm.device:
                    kante(vk, reg(vm.device), "gebunden an Host")
            for d in Device.objects.filter(cluster__isnull=False).select_related("cluster"):
                kante(reg(d.cluster), reg(d), "Host")
            for f in PowerFeed.objects.select_related("power_panel"):
                kante(reg(f), reg(f.power_panel), "Unterverteilung")
            for pp in PowerPort.objects.filter(cable__isnull=False).select_related("device"):
                for ep in pp.connected_endpoints or []:
                    quelle = ep if isinstance(ep, PowerFeed) else getattr(ep, "device", None)
                    kante(reg(pp.device), reg(quelle), "Strom")

            hoch = dict(hoch)
            runter = umkehren(hoch)
            sk = reg(start_obj)
            max_t = data.get("tiefe") or 4

            # --- Ausgabe ---
            text = [f"{names[sk]}  ({start_obj._meta.verbose_name})", ""]

            def abschnitt(titel, pfeil, adj):
                self.log_info(f"===== {titel} =====")
                text.append(titel)
                zeilen = baue_baum(sk, adj, max_t)
                if not zeilen:
                    self.log_info("(keine)")
                    text.append("  (keine)")
                for tiefe, k, label, hinweis in zeilen:
                    if hinweis == "Sammelzeile":
                        liste = ", ".join(sorted(names[x] for x in k))
                        zeile = f"{pfeil} {label}: {len(k)} Objekte ohne weitere Abhängigkeiten: {liste}"
                        self.log_info(f"{'·   ' * (tiefe - 1)}{zeile}")
                        text.append(f"{'    ' * tiefe}{zeile}")
                        continue
                    zusatz = f"  [{hinweis}]" if hinweis else ""
                    self.log_info(f"{'·   ' * (tiefe - 1)}{pfeil} {label}: {names[k]}{zusatz}",
                                  obj=objs[k])
                    text.append(f"{'    ' * tiefe}{pfeil} {label}: {names[k]}{zusatz}")
                text.append("")

            abschnitt("BENÖTIGT (wovon hängt das Objekt ab?)", "→", hoch)
            abschnitt("WIRD BENÖTIGT VON (wer hängt vom Objekt ab?)", "←", runter)

            if data.get("verkabelung") and isinstance(start_obj, Device):
                self.log_info("===== DIREKT VERKABELT MIT =====")
                text.append("DIREKT VERKABELT MIT")
                for itf in Interface.objects.filter(device=start_obj, cable__isnull=False):
                    for ep in itf.connected_endpoints or []:
                        peer = getattr(ep, "device", None) or getattr(ep, "circuit", None)
                        if peer is None:
                            continue
                        zeile = f"{itf.name} ↔ {peer} ({ep})"
                        self.log_info(zeile, obj=peer)
                        text.append(f"    {zeile}")

            return "\n".join(text)
