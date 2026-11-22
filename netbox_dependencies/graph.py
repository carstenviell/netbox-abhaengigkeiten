"""
Load the dependency graph from NetBox (core objects + plugin models) into the plain data
structures of engine.py. Ported from the former custom scripts; read-only.
"""
from collections import defaultdict

from django.utils.translation import gettext as _

from circuits.models import Circuit
from dcim.models import Device, Interface, PowerFeed, PowerPanel, PowerPort
from virtualization.models import Cluster, VirtualMachine

from .choices import DependencyTypeChoices
from .models import Dependency, RedundancyGroup


def key(obj):
    return (obj._meta.label_lower, obj.pk) if obj is not None else None


def endpoints(itf):
    """
    Peers of a cabled interface. If a circuit is terminated on one side only (typical for an internet
    uplink without documented provider side), NetBox considers the cable path incomplete and
    connected_endpoints is empty. Then the circuit termination at the end of the path counts
    (also across patch panels).
    """
    eps = itf.connected_endpoints or []
    path = getattr(itf, '_path', None)
    if not eps and path is not None and path.path_objects:
        eps = [o for o in path.path_objects[-1] if getattr(o, 'circuit', None) is not None]
    return eps


class Registry:
    """Collects objects by key and their display names."""

    def __init__(self):
        self.objs, self.names = {}, {}

    def __call__(self, obj):
        if obj is None:
            return None
        k = key(obj)
        if k not in self.objs:
            self.objs[k] = obj
            self.names[k] = str(obj)
        return k


def load_impact_graph(reg, no_ha_tag=''):
    """Returns kwargs for engine.compute_impact (without seeds/scenario) plus data-quality findings."""
    findings = []

    feed_panel = {reg(f): reg(f.power_panel) for f in PowerFeed.objects.select_related('power_panel')}
    device_power = defaultdict(list)
    for pp in PowerPort.objects.filter(cable__isnull=False).select_related('device'):
        sources = []
        for ep in pp.connected_endpoints or []:
            if isinstance(ep, PowerFeed):
                sources.append(reg(ep))
            elif getattr(ep, 'device', None) is not None:  # PDU outlet
                sources.append(reg(ep.device))
        device_power[reg(pp.device)].append(sources)

    device_links = defaultdict(list)
    for itf in Interface.objects.filter(cable__isnull=False).select_related('device'):
        for ep in endpoints(itf):
            if getattr(ep, 'device', None) is not None:
                device_links[reg(itf.device)].append(reg(ep.device))
            elif getattr(ep, 'circuit', None) is not None:
                device_links[reg(itf.device)].append(reg(ep.circuit))

    cluster_hosts = defaultdict(list)
    for d in Device.objects.filter(cluster__isnull=False).select_related('cluster'):
        cluster_hosts[reg(d.cluster)].append(reg(d))

    no_ha_tag = (no_ha_tag or '').strip()
    vms = []
    for vm in VirtualMachine.objects.select_related('cluster', 'device').prefetch_related('tags'):
        if no_ha_tag and vm.device is None and any(t.slug == no_ha_tag for t in vm.tags.all()):
            findings.append((_('VM %(vm)s is tagged "%(tag)s" but has no host – binding unknown.')
                             % {'vm': vm, 'tag': no_ha_tag}, vm))
        vms.append((reg(vm), reg(vm.cluster), reg(vm.device), vm.device is not None))

    groups = []
    for g in RedundancyGroup.objects.prefetch_related('members'):
        members = [reg(m.member) for m in g.members.all() if m.member is not None]
        groups.append((reg(g), members, g.min_active or 1))

    edges, broken = [], 0
    for e in Dependency.objects.all():
        if e.source is None or e.target is None:
            broken += 1
            continue
        edges.append((reg(e.source), reg(e.target), e.criticality or 'hard'))

    graph = dict(names=reg.names, feed_panel=feed_panel, device_power=dict(device_power),
                 device_links=dict(device_links), cluster_hosts=dict(cluster_hosts), vms=vms,
                 groups=groups, edges=edges)
    return graph, broken, findings


def load_tree_graph(reg):
    """{key: [(neighbour_key, label)]} for "X requires Y"."""
    up = defaultdict(list)

    def edge(a, b, label):
        if a is not None and b is not None:
            up[a].append((b, label))

    types = dict(DependencyTypeChoices.CHOICES)
    from .choices import CriticalityChoices
    crit = {c[0]: c[1] for c in CriticalityChoices.CHOICES}
    for e in Dependency.objects.all():
        if e.source is None or e.target is None:
            continue
        edge(reg(e.source), reg(e.target), f'{types.get(e.type, e.type)} [{crit.get(e.criticality, e.criticality)}]')
    for g in RedundancyGroup.objects.prefetch_related('members'):
        for m in g.members.all():
            edge(reg(g), reg(m.member), _('member (min. %(n)s active)') % {'n': g.min_active})
    for vm in VirtualMachine.objects.select_related('cluster', 'device'):
        if vm.cluster:
            edge(reg(vm), reg(vm.cluster), _('runs in cluster'))
        if vm.device:
            edge(reg(vm), reg(vm.device), _('bound to host'))
    for d in Device.objects.filter(cluster__isnull=False).select_related('cluster'):
        edge(reg(d.cluster), reg(d), _('host'))
    for f in PowerFeed.objects.select_related('power_panel'):
        edge(reg(f), reg(f.power_panel), _('power panel'))
    for pp in PowerPort.objects.filter(cable__isnull=False).select_related('device'):
        for ep in pp.connected_endpoints or []:
            source = ep if isinstance(ep, PowerFeed) else getattr(ep, 'device', None)
            edge(reg(pp.device), reg(source), _('power'))
    return {k: [(nb, str(label)) for nb, label in v] for k, v in up.items()}


SEED_MODELS = {  # form field / GET parameter -> model (parameter names are an interface, see README)
    'device': Device, 'virtualmachine': VirtualMachine, 'cluster': Cluster,
    'powerpanel': PowerPanel, 'powerfeed': PowerFeed, 'circuit': Circuit,
}
