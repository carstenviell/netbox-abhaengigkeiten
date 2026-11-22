"""
Impact and dependency-tree engine. Pure functions on hashable keys - no NetBox/ORM access,
so the scenario tests run without a database. Ported 1:1 from the former custom script
(impact_analyse.py, v1.0.6); only names and texts changed (English, translatable).

Propagation rules
  Power      power panel -> power feed -> device (a device fails when ALL connected power ports
             have no source left; a PDU outlet counts as a source)
  Cabling    a device is isolated (outage) when ALL cabled peers have failed. Partly affected
             devices are not guessed - redundancy is modelled with redundancy groups.
  Cluster    outage when fewer than the majority of votes (hosts + QDevice) is available.
  VMs        a VM with a host (device) set is bound to that host (no HA / pinned) and fails with
             it. A VM with only a cluster set is an HA VM and depends on the cluster only.
  Groups     outage below min_active available members, degraded as soon as one is missing.
  Edges      dependency source -> target with criticality
               hard      -> source inherits the state of the target
               degraded  -> source becomes degraded at most
               none      -> no effect
"""
from collections import defaultdict

from django.utils.translation import gettext as _

OUTAGE = 2
DEGRADED = 1


def level_text(level):
    return {OUTAGE: _('outage'), DEGRADED: _('degraded')}[level]


def compute_impact(seeds, names, feed_panel, device_power, device_links, cluster_hosts, vms, groups, edges,
                   scenario='outage', qdevice_votes=0):
    """
    All objects are referenced by hashable keys.
      seeds         [key]                       starting objects
      names         {key: str}                  display names
      feed_panel    {feed_key: panel_key}
      device_power  {dev_key: [[source_key, ...] per connected power port]}
      device_links  {dev_key: [peer_key per cabled interface]}
      cluster_hosts {cluster_key: [dev_key]}
      vms           [(vm_key, cluster_key|None, dev_key|None, bound: bool)]
      groups        [(group_key, [member_key], min_active)]
      edges         [(source_key, target_key, criticality)]
    Returns (state {key: level}, reason {key: str}, hints [str]).
    """
    state, reason, hints = {}, {}, []

    def n(k):
        return names.get(k, str(k))

    def level(k):
        return state.get(k, 0)

    def mark(k, lvl, why):
        if k is None or level(k) >= lvl:
            return False
        state[k] = lvl
        reason[k] = why
        return True

    for k in seeds:
        mark(k, OUTAGE, _('starting object'))

    for _round in range(1000):  # fixpoint iteration; states only rise monotonically
        changed = False

        # Power: power panel -> power feed
        for feed, panel in feed_panel.items():
            if panel is not None and level(panel) == OUTAGE:
                changed |= mark(feed, OUTAGE, _('power panel %(name)s failed') % {'name': n(panel)})

        # Power: device without a supplied power port
        for dev, ports in device_power.items():
            ports = [p for p in ports if p]
            if ports and all(all(level(q) == OUTAGE for q in p) for p in ports):
                changed |= mark(dev, OUTAGE, _('no power supply left (all power ports)'))

        # Cabling: all peers gone -> isolated
        for dev, peers in device_links.items():
            peers = [p for p in peers if p is not None]
            if peers and all(level(p) == OUTAGE for p in peers):
                changed |= mark(dev, OUTAGE, _('isolated: all cabled peers failed'))

        # Cluster quorum (QDevice votes count as available)
        for cl, hosts in cluster_hosts.items():
            if not hosts:
                continue
            votes = len(hosts) + qdevice_votes
            available = sum(1 for h in hosts if level(h) != OUTAGE) + qdevice_votes
            needed = votes // 2 + 1
            if available < needed:
                changed |= mark(cl, OUTAGE, _('quorum lost (%(available)s of %(votes)s votes, %(needed)s needed)')
                                % {'available': available, 'votes': votes, 'needed': needed})

        # VMs: with host = bound to the host (no HA / pinned), without host = HA, cluster only
        for vm, cl, dev, bound in vms:
            if cl is not None and level(cl) == OUTAGE:
                changed |= mark(vm, OUTAGE, _('cluster %(name)s failed') % {'name': n(cl)})
            elif dev is not None and bound and level(dev) == OUTAGE:
                changed |= mark(vm, OUTAGE, _('bound to host %(name)s (no HA / pinned)') % {'name': n(dev)})

        # Redundancy groups
        for grp, members, min_active in groups:
            if not members:
                continue
            available = sum(1 for m in members if level(m) != OUTAGE)
            if available < (min_active or 1):
                changed |= mark(grp, OUTAGE, _('only %(available)s of %(total)s available, at least %(min)s needed')
                                % {'available': available, 'total': len(members), 'min': min_active})
            elif available < len(members):
                changed |= mark(grp, DEGRADED, _('redundancy reduced (%(available)s of %(total)s available)')
                                % {'available': available, 'total': len(members)})

        # Dependency edges
        for source, target, criticality in edges:
            lvl = level(target)
            if not lvl or criticality == 'none':
                continue
            changed |= mark(source, lvl if criticality == 'hard' else DEGRADED,
                            _('requires %(name)s (%(level)s)') % {'name': n(target), 'level': level_text(lvl)})

        if not changed:
            break

    # Hints for HA VMs: their current host is deliberately not documented
    for cl, hosts in cluster_hosts.items():
        down = [h for h in hosts if level(h) == OUTAGE]
        if not down or level(cl) == OUTAGE:
            continue
        ha_vms = [vm for vm, c, dev, bound in vms if c == cl and level(vm) != OUTAGE and not (dev is not None and bound)]
        if not ha_vms:
            continue
        ctx = {'cluster': n(cl), 'hosts': ', '.join(n(h) for h in down), 'count': len(ha_vms),
               'remaining': len(hosts) - len(down)}
        if scenario == 'outage':
            hints.append(_('Cluster %(cluster)s: outage of %(hosts)s – HA VMs that ran there are restarted (short '
                           'interruption). Up to %(count)s HA VMs may be affected; which ones is not documented '
                           'in NetBox.') % ctx)
        else:
            hints.append(_('Cluster %(cluster)s: before maintenance of %(hosts)s, move HA VMs by live migration '
                           '(%(count)s HA VMs in the cluster). Check the capacity of the remaining %(remaining)s '
                           'host(s).') % ctx)

    return state, reason, hints


def find_cycles(edges):
    """Strongly connected components (Tarjan) that contain a cycle."""
    graph = defaultdict(list)
    for s, t, _c in edges:
        graph[s].append(t)
    index, low, stack, on_stack, result = {}, {}, [], set(), []
    counter = [0]

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in graph[v]:
                result.append(comp)

    for v in list(graph):
        if v not in index:
            visit(v)
    return result


# Tree markers (stable identifiers; the template translates them)
CYCLE, SEE_ABOVE, TRUNCATED, COLLAPSED = 'cycle', 'see_above', 'truncated', 'collapsed'


def build_tree(start, adj, max_depth=4):
    """
    adj: {key: [(neighbour_key, label)]}
    Returns [(depth, key, label, marker)]  marker: '' | CYCLE | SEE_ABOVE | TRUNCATED | COLLAPSED
    Every node is expanded once; repetitions are marked. For COLLAPSED, key is a tuple of keys.
    """
    rows, expanded = [], {start}

    def rec(k, depth, path):
        neighbours = adj.get(k, [])
        # leaves (no own neighbours) with the same label are collapsed from 4 on
        leaves = defaultdict(list)
        for nb, label in neighbours:
            if not adj.get(nb) and nb not in path and nb not in expanded:
                leaves[label].append(nb)
        collapse = {label for label, items in leaves.items() if len(items) > 3}
        collapsed = set()
        # nodes with a subtree first, collapsed rows after
        neighbours = sorted(neighbours, key=lambda x: 0 if adj.get(x[0]) else 1)
        for nb, label in neighbours:
            if label in collapse and nb in leaves[label]:
                if label not in collapsed:
                    collapsed.add(label)
                    rows.append((depth, tuple(leaves[label]), label, COLLAPSED))
                    expanded.update(leaves[label])
                continue
            if nb in path:
                rows.append((depth, nb, label, CYCLE))
            elif nb in expanded:
                rows.append((depth, nb, label, SEE_ABOVE))
            elif depth >= max_depth and adj.get(nb):
                rows.append((depth, nb, label, TRUNCATED))
            else:
                rows.append((depth, nb, label, ''))
                expanded.add(nb)
                rec(nb, depth + 1, path | {nb})

    rec(start, 1, {start})
    return rows


def invert(adj):
    reverse = defaultdict(list)
    for a, neighbours in adj.items():
        for b, label in neighbours:
            reverse[b].append((a, label))
    return dict(reverse)
