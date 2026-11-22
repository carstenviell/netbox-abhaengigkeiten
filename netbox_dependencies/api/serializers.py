from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from netbox.api.fields import ContentTypeField
from netbox.api.serializers import NetBoxModelSerializer

from ..choices import DEPENDENCY_MODELS_Q, GROUP_MEMBER_MODELS_Q
from ..models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember

BASE = 'plugins-api:netbox_dependencies-api:'


class BusinessProcessSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=BASE + 'businessprocess-detail')

    class Meta:
        model = BusinessProcess
        fields = ('id', 'url', 'display', 'name', 'owner', 'criticality', 'rto_hours', 'rpo_hours', 'mtpd_hours',
                  'nis2_relevant', 'bia_reference', 'description', 'comments', 'tags', 'custom_fields', 'created',
                  'last_updated')
        brief_fields = ('id', 'url', 'display', 'name', 'description')

    def validate(self, data):
        data = super().validate(data)
        rto = data.get('rto_hours', getattr(self.instance, 'rto_hours', None))
        mtpd = data.get('mtpd_hours', getattr(self.instance, 'mtpd_hours', None))
        if rto is not None and mtpd is not None and rto > mtpd:
            raise serializers.ValidationError({'rto_hours': 'RTO must not exceed MTPD.'})
        return data


class ApplicationSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=BASE + 'application-detail')

    class Meta:
        model = Application
        fields = ('id', 'url', 'display', 'name', 'vendor', 'owner', 'criticality', 'description', 'comments', 'tags',
                  'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display', 'name', 'description')


class RedundancyGroupSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=BASE + 'redundancygroup-detail')

    class Meta:
        model = RedundancyGroup
        fields = ('id', 'url', 'display', 'name', 'min_active', 'description', 'comments', 'tags', 'custom_fields',
                  'created', 'last_updated')
        brief_fields = ('id', 'url', 'display', 'name', 'description')


def _check_object(serializer, model_ct, object_id, field):
    """The object must exist AND be visible to the requesting user (no existence oracle for hidden objects)."""
    model = model_ct.model_class()
    request = serializer.context.get('request')
    qs = model.objects.all() if model is not None else None
    if qs is not None and request is not None and hasattr(qs, 'restrict'):
        qs = qs.restrict(request.user, 'view')
    if qs is None or not qs.filter(pk=object_id).exists():
        raise serializers.ValidationError({field: 'Object not found.'})


class RedundancyGroupMemberSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=BASE + 'redundancygroupmember-detail')
    member_type = ContentTypeField(queryset=ContentType.objects.filter(GROUP_MEMBER_MODELS_Q))

    class Meta:
        model = RedundancyGroupMember
        fields = ('id', 'url', 'display', 'group', 'member_type', 'member_id', 'tags', 'custom_fields', 'created',
                  'last_updated')
        brief_fields = ('id', 'url', 'display', 'group', 'member_type', 'member_id')

    def validate(self, data):
        data = super().validate(data)
        _check_object(self, data.get('member_type') or self.instance.member_type,
                      data.get('member_id', getattr(self.instance, 'member_id', None)), 'member_id')
        return data


class DependencySerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=BASE + 'dependency-detail')
    source_type = ContentTypeField(queryset=ContentType.objects.filter(DEPENDENCY_MODELS_Q))
    target_type = ContentTypeField(queryset=ContentType.objects.filter(DEPENDENCY_MODELS_Q))

    class Meta:
        model = Dependency
        fields = ('id', 'url', 'display', 'source_type', 'source_id', 'target_type', 'target_id', 'type',
                  'criticality', 'comment', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display', 'source_type', 'source_id', 'target_type', 'target_id', 'type')

    def validate(self, data):
        data = super().validate(data)
        for side in ('source', 'target'):
            _check_object(self, data.get(f'{side}_type') or getattr(self.instance, f'{side}_type'),
                          data.get(f'{side}_id', getattr(self.instance, f'{side}_id', None)), f'{side}_id')
        return data
