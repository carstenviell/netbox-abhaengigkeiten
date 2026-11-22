**English** | [Deutsch](CHANGELOG.de.md)

# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [SemVer](https://semver.org/).
Up to 1.x: schema versions per custom object type according to PEP 440, Git tag `schema-<version>`.

## [Unreleased]
### Security
- Impact analysis: reasons and migration hints (page and CSV export) named the objects that caused a failure, even if the user may not view them (e.g. a redundancy group behind a visible application). Names of hidden objects now appear as "(hidden object)". Found in a second security review; regression test `test_reasons_mask_hidden_objects`.

## Open

### Roadmap
1. Upgrade the production NetBox to 4.7 as a separate change with backup and fallback plan; then roll out plugin 2.0.
2. Complete the data: hosts with cluster assignment, cabling, power (power panel → power feed → power port).
3. Model a pilot process completely.
4. **Hypervisor sync** (e.g. Proxmox) on a schedule: never destructive, only report deviations; take over the HA state, set `device` only for VMs without HA.
5. **Backup check:** application with RPO → VMs → backup jobs; missing or too infrequent backups as findings.

Data findings are **not** kept in the repository (security relevant).

---

## [2.0.0] – 2026-11-22
The dependency model becomes the **NetBox plugin netbox-dependencies** (repository renamed from netbox-abhaengigkeiten; old links redirect).

### Added
- Own models business process, application, redundancy group (with members), dependency – with list, detail, edit, bulk import/delete, REST API and search. RTO ≤ MTPD is now validated when saving.
- Impact analysis and dependency tree as plugin pages instead of custom scripts, with CSV export; *Dependencies* panel on the detail pages of devices, VMs, clusters, circuits, power panels, power feeds and services.
- Permissions: the analysis runs on the complete infrastructure but only shows objects the user may view (only their number otherwise).
- Multilingual: English user interface with a shipped German translation, language per user, otherwise English.
- Management command `import_custom_objects` takes over the data of 1.x (dry run without `--commit`, idempotent). Verified on the test instance: all 23 objects imported; the impact analysis returns exactly the same 65 results as the former script in 7 comparison scenarios.

### Changed
- **Breaking:** no dependency on the NetBox Custom Objects plugin anymore; choice values are English (`runs_on`, `requires`, `authenticates_via`, `data_from`, `power_cooling`; `hard`, `degraded`, `none`).
- **Breaking:** interface for other plugins: `/plugins/dependencies/impact/?scenario=outage|maintenance&device=…&virtualmachine=…` instead of the script `ImpactAnalyse` with `szenario`/`devices`/`vms`.
- Engine taken over unchanged (all 15 scenario tests), only identifiers and texts are English and translatable.

### Removed
- `impact_analyse.py` (custom scripts), `setup_abhaengigkeiten.py`, `abhaengigkeiten_schema.yaml`, `tests/test_engine.py` (tests now run in the plugin).

### Security
- Security audit before the release (report kept locally): the detail-page panel does not show peers the user may not view; the API does not reveal whether IDs of invisible objects exist; CSV export protected against formula injection.

## [1.0.6] – 2026-11-22
### Documentation
- **README:** connection to the plugin `netbox-patch-management`. The script name `ImpactAnalyse` and the fields `szenario`, `devices`, `vms` are now an interface and must not be renamed.

## [1.0.5] – 2026-11-21
### Added
- **README:** custom links "Impact-Analyse" for device, VM, cluster, power panel, power feed and circuit (`?devices=`, `?vms=`, `?clusters=`, `?powerpanels=`, `?powerfeeds=`, `?circuits=` with `{{ object.pk }}`). The object is preselected in the form.
### Changed
- Prefilling the script form from GET parameters verified on NetBox 4.7. This also closes the open item on the custom links "Abhängigkeiten".

## [1.0.4] – 2026-11-16
### Fixed
- **Impact analysis / dependency tree:** circuits terminated on one side only (e.g. internet uplink without documented provider side) are recognised as peers. NetBox returns no `connected_endpoints` for such incomplete cable paths. So far a firewall therefore counted as isolated as soon as its only LAN switch failed, and a failed circuit had no effect on the connected device. Now the circuit termination at the end of the path counts (`CablePath.path_objects`, also across patch panels).
- Tests: scenario 15 (peers).

## [1.0.3] – 2026-11-16
### Fixed
- **Impact analysis:** affected processes and applications with level OUTAGE are logged as warnings instead of failures. So far NetBox set the job status to "failed" although the analysis ran correctly. `log_failure` is reserved for real errors (no starting object, custom object types not loadable, object not found). The level is still shown in the text and the CSV.

## [1.0.2] – 2026-11-16
### Fixed
- **Dependency tree:** if the plugin or the custom object types `abhaengigkeit`/`redundanzgruppe` are missing, the script stops with a clear message instead of `KeyError`/`ImportError` (same behaviour as the impact analysis).
- **Tests:** the misleading intermediate output "alle 9 Szenarien OK" now reads "Szenarien 1–9 OK".

## [1.0.1] – 2026-11-16
### Publication
- **Added:** published as public GitHub repository, release `v1.0.1`.
- **Changed:** `.gitignore` additionally excludes `CLAUDE.md` and `.DS_Store`.
- **Removed:** reference to `CLAUDE.md` in `README.md` (the file is not part of the repository).

## [1.0.0] – 2026-11-08
### Documentation
- **Added:** license Apache-2.0 (`LICENSE`, SPDX headers in the Python files).
- **Added:** `README.md` for publication. Internal findings and environment details moved to `INTERN.md` (not versioned).

### Schema 1.1.0 (`abhaengigkeit`)
- **Added:** `custom-objects/redundanzgruppe` as source type. This allows group-to-group dependencies such as DIST → CORE.
- Status: applied on the test instance. This confirms that the plugin allows extending `related_object_types` of an existing polymorphic field.

### Impact analysis / dependency tree (`impact_analyse.py`)
- **Added:** script **dependency tree**. It shows "requires" and "required by" over several levels, plus direct cabling. Repetitions are marked, end points from four on are collapsed into one row, objects with a subtree come first.
- **Changed:** the VM logic now follows the convention "host set = bound, only cluster = HA". The tag `kein-ha` is only used for a plausibility check. For HA VMs there are notes per cluster (restart or live migration) instead of a rating per VM.
- **Added:** parameter "QDevice votes per cluster". The first log line shows the starting objects.
- **Changed:** the CSV output uses readable type names instead of internal model names.
- **Added:** impact analysis with propagation via power, cabling, cluster quorum, VMs, redundancy groups and dependency edges. Plus data-quality checks and CSV export.
- Tests: 14 scenarios in `tests/test_engine.py`.
- Verified on the test instance: loading the custom objects, polymorphic fields, select values, reading group members, criticality "degraded", bound VM on host outage, isolation via cabling.

### Platform
- **Changed:** test instance upgraded from NetBox 4.5.4 to **4.7**. Reason: plugin 1.0.0 breaks in list views on 4.5.4 (`_apply_prefetching`).

### Schema 1.0.0 (all types)
- **Added:** types `geschaeftsprozess`, `applikation`, `redundanzgruppe`, `abhaengigkeit`. Choice sets `abhaengigkeit_typ` and `kritikalitaet`.
- **Added:** targets of a dependency are application, redundancy group, business process, VM, cluster, device, power feed, power panel, service and circuit.
- **Removed** before the first apply: `error_message` on unique constraints, because the plugin does not allow it there.
- Tested: re-running changes nothing (`has_changes: false`), uniqueness (source, target, type) is enforced, deletion protection works for source and target.

### Setup (`setup_abhaengigkeiten.py`)
- **Added:** create or check choice sets (never overwrite), preview, apply after confirmation with `ja`, destructive changes are refused.
- **Fixed:** the preview expects the document directly as body, applying expects it wrapped in `{"schema": …}`.
