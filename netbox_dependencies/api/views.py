from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets
from ..models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember
from . import serializers


class BusinessProcessViewSet(NetBoxModelViewSet):
    queryset = BusinessProcess.objects.all()
    serializer_class = serializers.BusinessProcessSerializer
    filterset_class = filtersets.BusinessProcessFilterSet


class ApplicationViewSet(NetBoxModelViewSet):
    queryset = Application.objects.all()
    serializer_class = serializers.ApplicationSerializer
    filterset_class = filtersets.ApplicationFilterSet


class RedundancyGroupViewSet(NetBoxModelViewSet):
    queryset = RedundancyGroup.objects.all()
    serializer_class = serializers.RedundancyGroupSerializer
    filterset_class = filtersets.RedundancyGroupFilterSet


class RedundancyGroupMemberViewSet(NetBoxModelViewSet):
    queryset = RedundancyGroupMember.objects.select_related('group', 'member_type')
    serializer_class = serializers.RedundancyGroupMemberSerializer
    filterset_class = filtersets.RedundancyGroupMemberFilterSet


class DependencyViewSet(NetBoxModelViewSet):
    queryset = Dependency.objects.select_related('source_type', 'target_type')
    serializer_class = serializers.DependencySerializer
    filterset_class = filtersets.DependencyFilterSet
