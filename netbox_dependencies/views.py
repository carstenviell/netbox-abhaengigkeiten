import csv

from django.apps import apps
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l
from django.views import View

from dcim.models import Device, Interface
from extras.ui.panels import CustomFieldsPanel, TagsPanel
from netbox.ui import attrs, layout
from netbox.ui.panels import CommentsPanel, ObjectAttributesPanel, ObjectsTablePanel
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, tables
from .choices import DEPENDENCY_MODELS, ScenarioChoices
from .engine import COLLAPSED, OUTAGE, build_tree, compute_impact, find_cycles, invert, level_text
from .graph import SEED_MODELS, Registry, endpoints, load_impact_graph, load_tree_graph
from .models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember

PERM_VIEW = 'netbox_dependencies.view_dependency'


# ---------------------------------------------------------------------------
# Detail panels
# ---------------------------------------------------------------------------

class BusinessProcessPanel(ObjectAttributesPanel):
    name = attrs.TextAttr('name')
    owner = attrs.RelatedObjectAttr('owner', linkify=True, label=_l('Process owner'))
    criticality = attrs.ChoiceAttr('criticality')
    rto_hours = attrs.NumericAttr('rto_hours', label=_l('RTO (hours)'))
    rpo_hours = attrs.NumericAttr('rpo_hours', label=_l('RPO (hours)'))
    mtpd_hours = attrs.NumericAttr('mtpd_hours', label=_l('MTPD (hours)'))
    nis2_relevant = attrs.BooleanAttr('nis2_relevant', label=_l('NIS2 relevant'))
    bia_reference = attrs.TextAttr('bia_reference', label=_l('BIA reference'))
    description = attrs.TextAttr('description')


class ApplicationPanel(ObjectAttributesPanel):
    name = attrs.TextAttr('name')
    vendor = attrs.TextAttr('vendor')
    owner = attrs.RelatedObjectAttr('owner', linkify=True, label=_l('Application owner'))
    criticality = attrs.ChoiceAttr('criticality')
    description = attrs.TextAttr('description')


class RedundancyGroupPanel(ObjectAttributesPanel):
    name = attrs.TextAttr('name')
    min_active = attrs.NumericAttr('min_active', label=_l('Minimum active'))
    description = attrs.TextAttr('description')


class RedundancyGroupMemberPanel(ObjectAttributesPanel):
    group = attrs.RelatedObjectAttr('group', linkify=True)
    member = attrs.GenericForeignKeyAttr('member', linkify=True, label=_l('Member'))


class DependencyPanel(ObjectAttributesPanel):
    source = attrs.GenericForeignKeyAttr('source', linkify=True, label=_l('Source (depends on the target)'))
    type = attrs.ChoiceAttr('type')
    target = attrs.GenericForeignKeyAttr('target', linkify=True, label=_l('Target (is required)'))
    criticality = attrs.ChoiceAttr('criticality')
    comment = attrs.TextAttr('comment')


def _crud(model, *, filterset, filterset_form, table, form, panel, import_form=None, bottom=None,
          template_name=None):
    """Register list/detail/add/edit/delete/bulk views for a model (NetBox 4.7 pattern)."""
    name = model.__name__

    @register_model_view(model, 'list', path='', detail=False)
    class ListView(generic.ObjectListView):
        queryset = model.objects.all()
    ListView.filterset, ListView.filterset_form, ListView.table = filterset, filterset_form, table

    @register_model_view(model)
    class DetailView(generic.ObjectView):
        queryset = model.objects.all()
        layout = layout.SimpleLayout(left_panels=[panel(), TagsPanel()],
                                     right_panels=[CommentsPanel(), CustomFieldsPanel()] if hasattr(model, 'comments')
                                     else [CustomFieldsPanel()],
                                     bottom_panels=bottom or [])
    if template_name:
        DetailView.template_name = template_name

    @register_model_view(model, 'add', detail=False)
    @register_model_view(model, 'edit')
    class EditView(generic.ObjectEditView):
        queryset = model.objects.all()
    EditView.form = form

    @register_model_view(model, 'delete')
    class DeleteView(generic.ObjectDeleteView):
        queryset = model.objects.all()

    @register_model_view(model, 'bulk_delete', path='delete', detail=False)
    class BulkDeleteView(generic.BulkDeleteView):
        queryset = model.objects.all()
    BulkDeleteView.filterset, BulkDeleteView.table = filterset, table

    if import_form:
        @register_model_view(model, 'bulk_import', path='import', detail=False)
        class BulkImportView(generic.BulkImportView):
            queryset = model.objects.all()
        BulkImportView.model_form = import_form

    for cls in (ListView, DetailView, EditView, DeleteView, BulkDeleteView):
        cls.__name__ = cls.__qualname__ = f'{name}{cls.__name__}'


def _deps_panel(title, field):
    return ObjectsTablePanel('netbox_dependencies.dependency', title=title, filters={
        f'{field}_type': lambda ctx: ctx['object']._meta.label_lower, f'{field}_id': lambda ctx: ctx['object'].pk})


_REQUIRES = _deps_panel(_l('Requires'), 'source')
_REQUIRED_BY = _deps_panel(_l('Required by'), 'target')

_crud(BusinessProcess, filterset=filtersets.BusinessProcessFilterSet, filterset_form=forms.BusinessProcessFilterForm,
      table=tables.BusinessProcessTable, form=forms.BusinessProcessForm, panel=BusinessProcessPanel,
      import_form=forms.BusinessProcessImportForm, bottom=[_REQUIRES],
      template_name='netbox_dependencies/object_with_analysis.html')
_crud(Application, filterset=filtersets.ApplicationFilterSet, filterset_form=forms.ApplicationFilterForm,
      table=tables.ApplicationTable, form=forms.ApplicationForm, panel=ApplicationPanel,
      import_form=forms.ApplicationImportForm, bottom=[_REQUIRES, _REQUIRED_BY],
      template_name='netbox_dependencies/object_with_analysis.html')
_crud(RedundancyGroup, filterset=filtersets.RedundancyGroupFilterSet, filterset_form=forms.RedundancyGroupFilterForm,
      table=tables.RedundancyGroupTable, form=forms.RedundancyGroupForm, panel=RedundancyGroupPanel,
      import_form=forms.RedundancyGroupImportForm,
      bottom=[ObjectsTablePanel('netbox_dependencies.redundancygroupmember', title=_l('Members'),
                                filters={'group_id': lambda ctx: ctx['object'].pk}), _REQUIRES, _REQUIRED_BY],
      template_name='netbox_dependencies/redundancygroup.html')
_crud(RedundancyGroupMember, filterset=filtersets.RedundancyGroupMemberFilterSet,
      filterset_form=forms.RedundancyGroupMemberFilterForm, table=tables.RedundancyGroupMemberTable,
      form=forms.RedundancyGroupMemberForm, panel=RedundancyGroupMemberPanel)
_crud(Dependency, filterset=filtersets.DependencyFilterSet, filterset_form=forms.DependencyFilterForm,
      table=tables.DependencyTable, form=forms.DependencyForm, panel=DependencyPanel)


# ---------------------------------------------------------------------------
# Analysis views
# ---------------------------------------------------------------------------

def visible(user, objs):
    """Keys of objects the user may view. The analysis runs on the whole graph, but only visible
    objects are shown (names of hidden objects are not disclosed)."""
    allowed = set()
    by_model = {}
    for k, obj in objs.items():
        by_model.setdefault(type(obj), []).append((k, obj.pk))
    for model, items in by_model.items():
        ok = set(model.objects.restrict(user, 'view').filter(pk__in=[pk for _k, pk in items])
                 .values_list('pk', flat=True))
        allowed.update(k for k, pk in items if pk in ok)
    return allowed


def visible_objects(user, objs):
    """Subset of objs (model instances) the user may view."""
    reg = Registry()
    keys = {reg(o): o for o in objs}
    ok = visible(user, reg.objs)
    return {o for k, o in keys.items() if k in ok}


def csv_safe(value):
    """Prevent CSV/formula injection when the export is opened in a spreadsheet."""
    value = str(value)
    return "'" + value if value[:1] in ('=', '+', '-', '@', '\t', '\r') else value


class ImpactView(PermissionRequiredMixin, View):
    permission_required = PERM_VIEW
    template_name = 'netbox_dependencies/impact.html'

    def get(self, request):
        form = forms.ImpactForm(request.GET or None, user=request.user)
        ctx = {'form': form}
        if form.is_bound and form.is_valid():
            seeds_objs = [o for field in SEED_MODELS for o in form.cleaned_data[field]]
            if seeds_objs:
                ctx.update(self.analyse(request, form.cleaned_data, seeds_objs))
                if request.GET.get('export') == 'csv':
                    return self.csv(ctx)
            else:
                ctx['no_seeds'] = True
        return render(request, self.template_name, ctx)

    def analyse(self, request, data, seeds_objs):
        reg = Registry()
        seeds = [reg(o) for o in seeds_objs]
        graph, broken, findings = load_impact_graph(reg, data.get('no_ha_tag'))
        qdevice = data.get('qdevice_votes') or 0
        show = visible(request.user, reg.objs)
        # reasons and hints name the causing objects - mask the ones the user may not see
        hidden_name = _('(hidden object)')
        graph['names'] = {k: (name if k in show else hidden_name) for k, name in reg.names.items()}
        state, reason, hints = compute_impact(seeds, scenario=data['scenario'], qdevice_votes=qdevice, **graph)
        proc, app = BusinessProcess._meta.label_lower, Application._meta.label_lower

        def rows(pred):
            keys = sorted((k for k in state if pred(k) and k in show), key=lambda k: (-state[k], reg.names[k]))
            return [{'obj': reg.objs[k], 'level': state[k], 'level_text': level_text(state[k]),
                     'outage': state[k] == OUTAGE, 'reason': reason[k],
                     'type': reg.objs[k]._meta.verbose_name} for k in keys]

        # data quality
        quality = [f for f in findings if reg(f[1]) in show]
        if broken:
            quality.append((_('%(n)s dependency(ies) without source/target.') % {'n': broken}, None))
        for comp in find_cycles(graph['edges']):
            if all(k in show for k in comp):
                quality.append((_('Cycle in dependencies: %(path)s') % {'path': ' → '.join(reg.names[k] for k in comp)},
                                None))
        for cl, hosts in graph['cluster_hosts'].items():
            if len(hosts) < 3 and not qdevice and cl in show:
                quality.append((_('Cluster %(cl)s has only %(n)s host(s) in NetBox and no QDevice – a host outage '
                                  'means quorum loss. Are hosts missing in NetBox?')
                                % {'cl': reg.names[cl], 'n': len(hosts)}, reg.objs[cl]))
        for vm, cl, dev, _bound in graph['vms']:
            if cl is None and dev is None and vm in show:
                quality.append((_('VM %(vm)s has neither cluster nor host.') % {'vm': reg.names[vm]}, reg.objs[vm]))

        hidden = sum(1 for k in state if k not in show)
        return {
            'scenario_label': dict(ScenarioChoices.CHOICES)[data['scenario']],
            'seed_objs': [reg.objs[k] for k in seeds],
            'processes': rows(lambda k: k[0] == proc),
            'applications': rows(lambda k: k[0] == app),
            'others': rows(lambda k: k[0] not in (proc, app) and k not in seeds),
            'hints': hints, 'quality': quality, 'hidden': hidden, 'analysed': True,
        }

    def csv(self, ctx):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="impact-analysis.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow([_('Level'), _('Type'), _('Object'), _('Reason')])
        for group in ('processes', 'applications', 'others'):
            for r in ctx[group]:
                writer.writerow([csv_safe(v) for v in (r['level_text'], r['type'], r['obj'], r['reason'])])
        return response


ALLOWED_TREE_MODELS = {f'{a}.{m}' for a, m in DEPENDENCY_MODELS}


class TreeView(PermissionRequiredMixin, View):
    permission_required = PERM_VIEW
    template_name = 'netbox_dependencies/tree.html'

    def get(self, request, app_label, model, pk):
        if f'{app_label}.{model}' not in ALLOWED_TREE_MODELS:
            raise Http404
        Model = apps.get_model(app_label, model)
        obj = get_object_or_404(Model.objects.restrict(request.user, 'view'), pk=pk)
        form = forms.TreeForm(request.GET or None)
        data = form.cleaned_data if form.is_bound and form.is_valid() else {'depth': 4, 'cabling': True}
        if not request.GET:
            data['cabling'] = True

        reg = Registry()
        start = reg(obj)
        up = load_tree_graph(reg)
        down = invert(up)
        show = visible(request.user, reg.objs)
        depth = data.get('depth') or 4

        def section(adj):
            out = []
            for d, k, label, marker in build_tree(start, adj, depth):
                if marker == COLLAPSED:
                    keys = [x for x in k if x in show]
                    out.append({'depth': d, 'label': label, 'marker': marker, 'collapsed': [reg.objs[x] for x in keys],
                                'hidden': len(k) - len(keys)})
                elif k in show:
                    out.append({'depth': d, 'label': label, 'marker': marker, 'obj': reg.objs[k]})
                else:
                    out.append({'depth': d, 'label': label, 'marker': 'hidden'})
            return out

        cabling = []
        if data.get('cabling') and isinstance(obj, Device):
            for itf in Interface.objects.restrict(request.user, 'view').filter(device=obj, cable__isnull=False):
                for ep in endpoints(itf):
                    peer = getattr(ep, 'device', None) or getattr(ep, 'circuit', None)
                    if peer is not None and reg(peer) in visible(request.user, {reg(peer): peer}):
                        cabling.append({'interface': itf, 'peer': peer, 'endpoint': ep})

        return render(request, self.template_name, {
            'object': obj, 'form': form, 'requires': section(up), 'required_by': section(down), 'cabling': cabling,
            'is_device': isinstance(obj, Device),
        })


def tree_url(obj):
    from django.urls import reverse
    return reverse('plugins:netbox_dependencies:tree', args=[obj._meta.app_label, obj._meta.model_name, obj.pk])


def impact_url(objs, scenario=ScenarioChoices.OUTAGE):
    """Link to the impact analysis with the objects preselected (used by other plugins, see README)."""
    from urllib.parse import urlencode

    from django.urls import reverse
    params = [('scenario', scenario)] + [(o._meta.model_name, o.pk) for o in objs
                                         if o._meta.model_name in SEED_MODELS]
    return f"{reverse('plugins:netbox_dependencies:impact')}?{urlencode(params)}"


def content_type_of(obj):
    return ContentType.objects.get_for_model(obj)
