from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from utilities.choices import ChoiceSet


class CriticalityChoices(ChoiceSet):
    HARD = 'hard'
    DEGRADED = 'degraded'
    NONE = 'none'

    CHOICES = (
        (HARD, _('Hard (outage)'), 'red'),
        (DEGRADED, _('Degraded'), 'orange'),
        (NONE, _('None'), 'gray'),
    )


class DependencyTypeChoices(ChoiceSet):
    RUNS_ON = 'runs_on'
    REQUIRES = 'requires'
    AUTHENTICATES_VIA = 'authenticates_via'
    DATA_FROM = 'data_from'
    POWER_COOLING = 'power_cooling'

    CHOICES = (
        (RUNS_ON, _('Runs on')),
        (REQUIRES, _('Requires')),
        (AUTHENTICATES_VIA, _('Authenticates via')),
        (DATA_FROM, _('Data from')),
        (POWER_COOLING, _('Power/cooling')),
    )


class ScenarioChoices(ChoiceSet):
    OUTAGE = 'outage'
    MAINTENANCE = 'maintenance'

    CHOICES = (
        (OUTAGE, _('Unplanned outage')),
        (MAINTENANCE, _('Planned maintenance (HA VMs are migrated)')),
    )


def _q(models):
    q = Q()
    for app_label, model in models:
        q |= Q(app_label=app_label, model=model)
    return q


# Objects that can be source or target of a dependency
DEPENDENCY_MODELS = (
    ('circuits', 'circuit'), ('dcim', 'device'), ('dcim', 'powerfeed'), ('dcim', 'powerpanel'),
    ('ipam', 'service'), ('virtualization', 'cluster'), ('virtualization', 'virtualmachine'),
    ('netbox_dependencies', 'businessprocess'), ('netbox_dependencies', 'application'),
    ('netbox_dependencies', 'redundancygroup'),
)
# Objects that can be members of a redundancy group
GROUP_MEMBER_MODELS = (
    ('dcim', 'device'), ('virtualization', 'virtualmachine'), ('virtualization', 'cluster'),
    ('circuits', 'circuit'),
)
DEPENDENCY_MODELS_Q = _q(DEPENDENCY_MODELS)
GROUP_MEMBER_MODELS_Q = _q(GROUP_MEMBER_MODELS)
