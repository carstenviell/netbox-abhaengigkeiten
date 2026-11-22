"""
Deletion protection (as `on_delete: protect` in the former schema): an object that is source or
target of a dependency cannot be deleted. Group memberships of a deleted object are removed.
"""
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _

from utilities.exceptions import AbortRequest

from .choices import DEPENDENCY_MODELS, GROUP_MEMBER_MODELS
from .models import Dependency, RedundancyGroupMember

_PROTECTED = {f'{a}.{m}' for a, m in DEPENDENCY_MODELS}
_MEMBERS = {f'{a}.{m}' for a, m in GROUP_MEMBER_MODELS}


@receiver(pre_delete)
def protect_dependency_objects(sender, instance, **kwargs):
    label = getattr(getattr(sender, '_meta', None), 'label_lower', None)
    if label not in _PROTECTED and label not in _MEMBERS:
        return
    ct = ContentType.objects.get_for_model(sender)
    if label in _PROTECTED:
        used = Dependency.objects.filter(source_type=ct, source_id=instance.pk).count() + \
            Dependency.objects.filter(target_type=ct, target_id=instance.pk).count()
        if used:
            raise AbortRequest(_('%(obj)s is used in %(n)s dependency(ies) and cannot be deleted. '
                                 'Remove the dependencies first.') % {'obj': instance, 'n': used})
    if label in _MEMBERS:
        RedundancyGroupMember.objects.filter(member_type=ct, member_id=instance.pk).delete()
