import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from netbox.tables import NetBoxTable, columns

from .models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember


class BusinessProcessTable(NetBoxTable):
    name = tables.Column(linkify=True)
    owner = tables.Column(linkify=True)
    criticality = columns.ChoiceFieldColumn()
    nis2_relevant = columns.BooleanColumn()
    tags = columns.TagColumn(url_name='plugins:netbox_dependencies:businessprocess_list')

    class Meta(NetBoxTable.Meta):
        model = BusinessProcess
        fields = ('pk', 'id', 'name', 'owner', 'criticality', 'rto_hours', 'rpo_hours', 'mtpd_hours', 'nis2_relevant',
                  'bia_reference', 'description', 'tags', 'created', 'last_updated')
        default_columns = ('name', 'owner', 'criticality', 'rto_hours', 'mtpd_hours', 'nis2_relevant')


class ApplicationTable(NetBoxTable):
    name = tables.Column(linkify=True)
    owner = tables.Column(linkify=True)
    criticality = columns.ChoiceFieldColumn()
    tags = columns.TagColumn(url_name='plugins:netbox_dependencies:application_list')

    class Meta(NetBoxTable.Meta):
        model = Application
        fields = ('pk', 'id', 'name', 'vendor', 'owner', 'criticality', 'description', 'tags', 'created',
                  'last_updated')
        default_columns = ('name', 'vendor', 'owner', 'criticality')


class RedundancyGroupTable(NetBoxTable):
    name = tables.Column(linkify=True)
    member_count = tables.Column(verbose_name=_('Members'), accessor='members__count', orderable=False,
                                 empty_values=())
    tags = columns.TagColumn(url_name='plugins:netbox_dependencies:redundancygroup_list')

    class Meta(NetBoxTable.Meta):
        model = RedundancyGroup
        fields = ('pk', 'id', 'name', 'min_active', 'member_count', 'description', 'tags', 'created', 'last_updated')
        default_columns = ('name', 'min_active', 'member_count', 'description')

    def render_member_count(self, record):
        return record.members.count()


class RedundancyGroupMemberTable(NetBoxTable):
    group = tables.Column(linkify=True)
    member_type = columns.ContentTypeColumn(verbose_name=_('Type'))
    member = tables.Column(linkify=True, orderable=False, verbose_name=_('Member'))

    class Meta(NetBoxTable.Meta):
        model = RedundancyGroupMember
        fields = ('pk', 'id', 'group', 'member_type', 'member', 'created', 'last_updated')
        default_columns = ('group', 'member_type', 'member')


class DependencyTable(NetBoxTable):
    id = tables.Column(linkify=True, verbose_name='ID')
    source_type = columns.ContentTypeColumn(verbose_name=_('Source type'))
    source = tables.Column(linkify=True, orderable=False, verbose_name=_('Source'))
    type = columns.ChoiceFieldColumn()
    target_type = columns.ContentTypeColumn(verbose_name=_('Target type'))
    target = tables.Column(linkify=True, orderable=False, verbose_name=_('Target'))
    criticality = columns.ChoiceFieldColumn()
    tags = columns.TagColumn(url_name='plugins:netbox_dependencies:dependency_list')

    class Meta(NetBoxTable.Meta):
        model = Dependency
        fields = ('pk', 'id', 'source_type', 'source', 'type', 'target_type', 'target', 'criticality', 'comment',
                  'tags', 'created', 'last_updated')
        default_columns = ('id', 'source', 'type', 'target', 'criticality', 'comment')
