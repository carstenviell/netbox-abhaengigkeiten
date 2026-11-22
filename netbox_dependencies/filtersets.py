import django_filters
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from netbox.filtersets import NetBoxModelFilterSet
from utilities.filters import ContentTypeFilter

from .choices import CriticalityChoices, DependencyTypeChoices
from .models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember


class _NamedFilterSet(NetBoxModelFilterSet):
    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class BusinessProcessFilterSet(_NamedFilterSet):
    criticality = django_filters.MultipleChoiceFilter(choices=CriticalityChoices)

    class Meta:
        model = BusinessProcess
        fields = ('id', 'name', 'owner', 'criticality', 'nis2_relevant', 'rto_hours', 'rpo_hours', 'mtpd_hours')


class ApplicationFilterSet(_NamedFilterSet):
    criticality = django_filters.MultipleChoiceFilter(choices=CriticalityChoices)

    class Meta:
        model = Application
        fields = ('id', 'name', 'vendor', 'owner', 'criticality')


class RedundancyGroupFilterSet(_NamedFilterSet):
    class Meta:
        model = RedundancyGroup
        fields = ('id', 'name', 'min_active')


class RedundancyGroupMemberFilterSet(NetBoxModelFilterSet):
    group_id = django_filters.ModelMultipleChoiceFilter(queryset=RedundancyGroup.objects.all(), label=_('Group'))
    member_type = ContentTypeFilter()

    class Meta:
        model = RedundancyGroupMember
        fields = ('id', 'group', 'member_type', 'member_id')

    def search(self, queryset, name, value):
        return queryset.filter(group__name__icontains=value) if value.strip() else queryset


class DependencyFilterSet(NetBoxModelFilterSet):
    type = django_filters.MultipleChoiceFilter(choices=DependencyTypeChoices)
    criticality = django_filters.MultipleChoiceFilter(choices=CriticalityChoices)
    source_type = ContentTypeFilter()
    target_type = ContentTypeFilter()

    class Meta:
        model = Dependency
        fields = ('id', 'type', 'criticality', 'source_type', 'source_id', 'target_type', 'target_id')

    def search(self, queryset, name, value):
        return queryset.filter(comment__icontains=value) if value.strip() else queryset
