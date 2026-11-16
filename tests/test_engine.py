# SPDX-License-Identifier: Apache-2.0
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from impact_analyse import berechne_impact, finde_zyklen, AUSFALL, DEGRADIERT

def basis():
    names = {}
    hosts = ["host-a","host-b","host-c"]
    cluster_hosts = {"cl": hosts}
    vms = [("vm-erp","cl",None,False), ("vm-proxy-a","cl","host-a",True),
           ("vm-db","cl",None,False)]
    device_power = {"host-a":[["feed1"],["feed2"]], "host-b":[["feed1"],["feed2"]],
                    "host-c":[["feed1"],["feed2"]], "sw1":[["feed1"]], "sw2":[["feed2"]]}
    feed_panel = {"feed1":"UV1","feed2":"UV2"}
    device_links = {"host-a":["sw1","sw2"],"host-b":["sw1","sw2"],"host-c":["sw1","sw2"],
                    "sw1":["host-a","host-b","host-c"],"sw2":["host-a","host-b","host-c"]}
    groups = [("grp-core",["sw1","sw2"],1)]
    edges = [("app-erp","vm-erp","hart"),("app-erp","vm-db","hart"),
             ("app-erp","grp-core","hart"),("proz-abr","app-erp","hart"),
             ("app-backup","vm-proxy-a","degradiert")]
    return dict(names=names, feed_panel=feed_panel, device_power=device_power,
                device_links=device_links, cluster_hosts=cluster_hosts, vms=vms,
                groups=groups, edges=edges)

def run(seeds, szen="ausfall", **over):
    d = basis(); d.update(over)
    return berechne_impact(seeds, szenario=szen, **d)

# 1 Ein Switch weg: Gruppe degradiert -> App + Prozess degradiert, keine Hosts isoliert
z,g,m = run(["sw1"])
assert z.get("grp-core")==DEGRADIERT and z.get("app-erp")==DEGRADIERT and z.get("proz-abr")==DEGRADIERT
assert "host-a" not in z, z
# 2 Beide Switches: Hosts isoliert -> Cluster weg -> alles Ausfall
z,g,m = run(["sw1","sw2"])
assert z["host-a"]==AUSFALL and z["cl"]==AUSFALL and z["proz-abr"]==AUSFALL, z
# 3 Host-Ausfall: HA-VM degradiert, Nicht-HA-VM Ausfall, Backup-App degradiert
z,g,m = run(["host-a"])
assert "vm-erp" not in z and z["vm-proxy-a"]==AUSFALL and z["app-backup"]==DEGRADIERT
assert "proz-abr" not in z and "cl" not in z
assert len(m)==1 and "neu gestartet" in m[0] and "bis zu 2" in m[0], m
# 4 Wartung Host: HA-VM nur migrieren
z,g,m = run(["host-a"], "wartung")
assert "vm-erp" not in z and z["vm-proxy-a"]==AUSFALL
assert len(m)==1 and "Live-Migration" in m[0], m
# 5 Zwei Hosts weg: Quorum verloren
z,g,m = run(["host-a","host-b"])
assert z["cl"]==AUSFALL and z["vm-db"]==AUSFALL and z["proz-abr"]==AUSFALL
# 6 UV1 weg: Feed1 weg, Hosts haben feed2 -> nur sw1 weg
z,g,m = run(["UV1"])
assert z["feed1"]==AUSFALL and z["sw1"]==AUSFALL and "host-a" not in z and z["grp-core"]==DEGRADIERT
# 7 Beide UVs: alles weg
z,g,m = run(["UV1","UV2"])
assert z["cl"]==AUSFALL and z["proz-abr"]==AUSFALL
# 8 Zyklus Prozess<->Prozess terminiert und wird erkannt
e = basis()["edges"] + [("p1","p2","hart"),("p2","p1","hart"),("p1","app-erp","hart")]
z,g,m = run(["sw1","sw2"], edges=e)
assert z["p1"]==AUSFALL and z["p2"]==AUSFALL
assert any(set(c)=={"p1","p2"} for c in finde_zyklen(e))
# 9 Kante "keine" ohne Wirkung
z,g,m = run(["host-a"], edges=[("x","vm-proxy-a","keine")])
assert "x" not in z
print("alle 9 Szenarien OK")
# 10 Zwei-Host-Cluster: ohne QDevice Quorumverlust, mit QDevice nicht
two = {"cl": ["host-a","host-b"]}
z,g,m = run(["host-a"], cluster_hosts=two)
assert z["cl"]==AUSFALL
d = basis(); d.update(cluster_hosts=two)
z,g,m = berechne_impact(["host-a"], szenario="ausfall", qdevice_stimmen=1, **d)
assert "cl" not in z and "vm-erp" not in z and len(m)==1
print("Szenario 10 (QDevice) OK")
# 11 Cluster weg: keine HA-Hinweise, alles Ausfall
z,g,m = run(["host-a","host-b"])
assert m==[] and z["vm-erp"]==AUSFALL
print("Szenario 11 OK")
# 12 Baum: ESX02 -> Gruppe -> Switches; Rückrichtung vom Switch
from impact_analyse import baue_baum, umkehren
hoch = {"esx2":[("grp","benötigt [hart]")], "esx1":[("grp","benötigt [hart]")],
        "grp":[("sw1","Mitglied"),("sw2","Mitglied")], "a":[("b","x")], "b":[("a","x")]}
z = baue_baum("esx2", hoch)
assert [(t,k) for t,k,_,_ in z]==[(1,"grp"),(2,"sw1"),(2,"sw2")], z
r = umkehren(hoch)
z = baue_baum("sw1", r)
assert [(t,k) for t,k,_,_ in z]==[(1,"grp"),(2,"esx2"),(2,"esx1")], z
z = baue_baum("a", hoch)
assert z[-1][3]=="Zyklus"
z = baue_baum("esx2", hoch, max_tiefe=1)
assert z==[(1,"grp","benötigt [hart]","…")], z
print("Szenario 12 (Baum) OK")
# 13 Sammelzeile: Cluster mit 5 Blatt-VMs + 1 VM mit App
hoch = {"vm%d"%i:[("cl","läuft im Cluster")] for i in range(5)}
hoch["vmx"]=[("cl","läuft im Cluster")]; hoch["app"]=[("vmx","läuft auf [hart]")]
hoch["cl"]=[("host","Host")]
z = baue_baum("host", umkehren(hoch))
assert z[0][1]=="cl" and z[1][1]=="vmx" and z[2][1]=="app", z
assert z[3][3]=="Sammelzeile" and len(z[3][1])==5, z
assert len(z)==4
print("Szenario 13 (Sammelzeile) OK")
# 14 Gruppe als Quelle: DIST-Gruppe benötigt CORE-Gruppe
g = [("grp-core",["c1","c2"],1),("grp-dist",["d1","d2"],1)]
e = [("grp-dist","grp-core","hart"),("host","grp-dist","hart")]
d = basis(); d.update(groups=g, edges=e, cluster_hosts={}, vms=[], device_links={}, device_power={})
z,_,_ = berechne_impact(["c1","c2"], **d)
assert z["grp-core"]==AUSFALL and z["grp-dist"]==AUSFALL and z["host"]==AUSFALL, z
z,_,_ = berechne_impact(["c1"], **d)
assert z["grp-dist"]==DEGRADIERT and z["host"]==DEGRADIERT, z
print("Szenario 14 (Gruppe als Quelle) OK")
