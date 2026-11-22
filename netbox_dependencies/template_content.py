from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from netbox.plugins import PluginTemplateExtension

from .graph import SEED_MODELS
from .models import Dependency
from .views import impact_url, tree_url, visible_objects

CORE_MODELS = ['circuits.circuit', 'dcim.device', 'dcim.powerfeed', 'dcim.powerpanel', 'ipam.service',
               'virtualization.cluster', 'virtualization.virtualmachine']


class DependencyPanel(PluginTemplateExtension):
    models = CORE_MODELS

    def right_page(self):
        obj, user = self.context['object'], self.context['request'].user
        if not user.has_perm('netbox_dependencies.view_dependency'):
            return ''
        ct = ContentType.objects.get_for_model(obj)
        deps = Dependency.objects.restrict(user, 'view').filter(
            Q(source_type=ct, source_id=obj.pk) | Q(target_type=ct, target_id=obj.pk))
        requires = [d for d in deps if (d.source_type_id, d.source_id) == (ct.pk, obj.pk)]
        required_by = [d for d in deps if (d.target_type_id, d.target_id) == (ct.pk, obj.pk)]
        # never disclose the name of an object the user may not view
        others = {d.target for d in requires if d.target is not None} | {d.source for d in required_by if d.source is not None}
        shown = visible_objects(user, others)
        hidden = sum(1 for d in requires if d.target not in shown) + sum(1 for d in required_by if d.source not in shown)
        requires = [d for d in requires if d.target in shown]
        required_by = [d for d in required_by if d.source in shown]
        return self.render('netbox_dependencies/inc/object_panel.html', extra_context={
            'requires': requires, 'required_by': required_by, 'tree_url': tree_url(obj),
            'impact_url': impact_url([obj]) if obj._meta.model_name in SEED_MODELS else None,
            'add_ct': f'{ct.pk}', 'hidden': hidden,
        })


template_extensions = [DependencyPanel]
