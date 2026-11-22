**English** | [Deutsch](README.de.md)

# NetBox Dependencies

[NetBox](https://github.com/netbox-community/netbox) plugin to document the dependencies between **business processes,
applications, VMs, clusters, network and power** – and to answer two questions from them: *what is affected when these
objects fail or are maintained?* and *what does this object depend on?*

Made for operations where these questions come up regularly:

- **Patch and update planning:** what is affected when this switch or host is maintained?
- **Business continuity (BCM):** which processes fail, in which order are they restored?
- **NIS2 / ISMS:** how do infrastructure outages affect critical processes – traceable and versioned.
- **Backup planning:** which systems are behind processes with RPO requirements?

## Features

**Data model**

| Object | Purpose |
|---|---|
| Business process | Process with BIA figures (RTO, RPO, MTPD), owner and NIS2 relevance. RTO must not exceed MTPD. |
| Application | Business application or IT service |
| Redundancy group | "At least N of M members must be available", e.g. a switch pair (members: devices, VMs, clusters, circuits) |
| Dependency | Directed edge "source requires target" with type (runs on, requires, authenticates via, data from, power/cooling) and criticality (hard / degraded / none) |

- A dependency exists only once per source, target and type.
- Objects used in a dependency cannot be deleted (remove the dependency first).
- Sources and targets: devices, VMs, clusters, circuits, power panels, power feeds, application services, business
  processes, applications and redundancy groups.

**Impact analysis** (*Dependencies → Impact analysis*, or the button on a device/VM/cluster/... page): choose objects
and a scenario (outage or maintenance). The result lists the affected business processes, applications and other
objects with the level *outage* or *degraded* and the reason, notes on HA VMs (restart / live migration) and data
quality findings; CSV export included. Propagation covers:

- **Power:** power panel → power feed → power port; a PDU counts as a source.
- **Cabling:** a device is isolated when all cabled peers have failed (also via one-sided circuits).
- **Cluster quorum:** majority of hosts, optionally with QDevice votes.
- **VMs:** a VM with a host set is bound to it; a VM with only a cluster set is an HA VM.
- **Redundancy groups:** level depends on the required minimum of active members.
- **Dependency edges:** the criticality decides what is passed on.

**Dependency tree** (button on every supported object): what the object *requires* and what it is *required by*, over
several levels, optionally with the direct cable connections.

**Detail pages** of devices, VMs, clusters, circuits, power panels/feeds and services show a *Dependencies* panel
with the direct dependencies and buttons for tree, impact analysis and "add dependency".

**Permissions are respected:** the analysis always runs on the complete infrastructure, but objects the user may not
view are never shown – only their number.

## Requirements

- NetBox **4.7** or later

## Installation

The plugin is not published on PyPI. Install it from the GitHub release archive – this works without `git`, also in the
netbox-docker image. Replace `v2.0.1` with the [release](https://github.com/carstenviell/netbox-dependencies/releases)
you want.

**NetBox installed from source (systemd):**

```bash
sudo /opt/netbox/venv/bin/pip install https://github.com/carstenviell/netbox-dependencies/archive/refs/tags/v2.0.1.tar.gz

# keep the plugin when NetBox is upgraded (upgrade.sh reinstalls local_requirements.txt)
echo "https://github.com/carstenviell/netbox-dependencies/archive/refs/tags/v2.0.1.tar.gz" | \
  sudo tee -a /opt/netbox/local_requirements.txt
```

**netbox-docker:** add to `plugin_requirements.txt`

```text
https://github.com/carstenviell/netbox-dependencies/archive/refs/tags/v2.0.1.tar.gz
```

and to `Dockerfile-Plugins` (build `netbox`, `netbox-worker` and `netbox-housekeeping` from it via `docker-compose.override.yml`):

```dockerfile
FROM netboxcommunity/netbox:v4.7
COPY ./plugin_requirements.txt /opt/netbox/
RUN /usr/local/bin/uv pip install -r /opt/netbox/plugin_requirements.txt
```

Enable the plugin in `configuration.py` (Docker: `configuration/plugins.py`):

```python
PLUGINS = [
    # ...
    'netbox_dependencies',
]
```

Apply the migrations and restart:

```bash
cd /opt/netbox/netbox
sudo /opt/netbox/venv/bin/python manage.py migrate
sudo systemctl restart netbox netbox-rq
```

Docker: `docker compose build --no-cache && docker compose up -d` – migrations run automatically at start.

### Permissions

| Task | Permission |
|---|---|
| Impact analysis, dependency tree, panel | `netbox_dependencies.view_dependency` |
| View / maintain the model | `view` / `add` / `change` / `delete` on business process, application, redundancy group (member), dependency |

Results only contain objects the user may view (object permissions apply).

### Upgrade

Install the new release archive (also update `local_requirements.txt` / `plugin_requirements.txt`), then `migrate`
and restart (Docker: rebuild).

### Migration from 1.x (custom objects + custom scripts)

Version 1.x was not a plugin: it used [NetBox Custom Objects](https://github.com/netboxlabs/netbox-custom-objects)
and two custom scripts. 2.0 brings its own models; the data is taken over with a management command (dry run unless
`--commit`, idempotent, the custom objects are not changed):

```bash
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py import_custom_objects            # dry run
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py import_custom_objects --commit   # import
```

Afterwards remove the old custom scripts and custom links; delete the custom object types once you have checked the
import. Other plugins linking the old script must use the new URL (see below).

### Interface for other plugins

The impact analysis can be opened preselected:
`/plugins/dependencies/impact/?scenario=outage|maintenance&device=<id>&virtualmachine=<id>&cluster=<id>&powerpanel=<id>&powerfeed=<id>&circuit=<id>`
(parameters may repeat). [netbox-patch-management](https://github.com/carstenviell/netbox-patch-management) uses it.

## Language

The user interface is English and ships with a German translation. It follows the language the user selected in
NetBox (*Profile → Preferences → Language*); languages without a translation fall back to English.

## Conventions

1. **VM binding:** a VM with a host set is bound to that host (no HA or pinned). A VM with only a cluster set is an
   HA VM. The impact analysis relies on this.
2. **Redundancy** is modelled with redundancy groups only – never guessed from the cabling.
3. **No duplicate edges:** VM → cluster, host → cluster, cabling and power are read from the NetBox core objects; do not
   add dependencies for them.

```
Business process "Billing"
  └─ requires [hard] → Application "ERP"
        ├─ runs on [hard] → VM "erp01" ─→ cluster ─→ hosts ─→ power
        ├─ authenticates via [hard] → Application "Active Directory"
        │     └─ runs on [hard] → Redundancy group "DCs" (min. 1 of 2)
        └─ requires [hard] → Redundancy group "Access switches" (min. 1 of 2)
              └─ requires [hard] → Redundancy group "Core switches" (min. 1 of 2)
```

## Limits

- **Conservative:** if a cluster loses quorum, all its VMs count as failed.
- **No capacity check:** whether the remaining hosts have enough resources is not checked.
- **Ceph** is not modelled separately; model a storage network with redundancy groups and dependencies.
- **The current host of HA VMs is deliberately not documented** – for a host outage the analysis gives one note per
  cluster.
- **Results are only as good as the data:** missing cabling, power ports or dependencies mean effects are not reported.

## Development

```bash
cd ~/dev/netbox/netbox-docker   # or your NetBox
python manage.py test netbox_dependencies --keepdb
```

The impact and tree engines (`engine.py`) are pure functions; their scenario tests need no database.

## License

[Apache License 2.0](LICENSE), the same license as NetBox.
