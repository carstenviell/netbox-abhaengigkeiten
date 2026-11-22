from django import forms
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _

from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm, NetBoxModelImportForm
from tenancy.models import Contact
from utilities.forms.fields import (CommentField, CSVChoiceField, DynamicModelChoiceField,
                                    DynamicModelMultipleChoiceField, GenericObjectChoiceField)
from utilities.forms.mixins import GenericObjectFormMixin
from utilities.forms.rendering import FieldSet

from .choices import CriticalityChoices, DEPENDENCY_MODELS_Q, DependencyTypeChoices, GROUP_MEMBER_MODELS_Q, ScenarioChoices
from .graph import SEED_MODELS
from .models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember


class BusinessProcessForm(NetBoxModelForm):
    owner = DynamicModelChoiceField(queryset=Contact.objects.all(), required=False, label=_('Process owner'))
    comments = CommentField()

    fieldsets = (
        FieldSet('name', 'owner', 'criticality', 'description', 'tags', name=_('Business process')),
        FieldSet('rto_hours', 'rpo_hours', 'mtpd_hours', 'nis2_relevant', 'bia_reference', name=_('Continuity')),
    )

    class Meta:
        model = BusinessProcess
        fields = ('name', 'owner', 'criticality', 'rto_hours', 'rpo_hours', 'mtpd_hours', 'nis2_relevant',
                  'bia_reference', 'description', 'comments', 'tags')


class ApplicationForm(NetBoxModelForm):
    owner = DynamicModelChoiceField(queryset=Contact.objects.all(), required=False, label=_('Application owner'))
    comments = CommentField()

    fieldsets = (FieldSet('name', 'vendor', 'owner', 'criticality', 'description', 'tags', name=_('Application')),)

    class Meta:
        model = Application
        fields = ('name', 'vendor', 'owner', 'criticality', 'description', 'comments', 'tags')


class RedundancyGroupForm(NetBoxModelForm):
    comments = CommentField()

    fieldsets = (FieldSet('name', 'min_active', 'description', 'tags', name=_('Redundancy group')),)

    class Meta:
        model = RedundancyGroup
        fields = ('name', 'min_active', 'description', 'comments', 'tags')


class RedundancyGroupMemberForm(GenericObjectFormMixin, NetBoxModelForm):
    group = DynamicModelChoiceField(queryset=RedundancyGroup.objects.all(), label=_('Group'))
    member = GenericObjectChoiceField(
        label=_('Member'), content_type_queryset=ContentType.objects.filter(GROUP_MEMBER_MODELS_Q),
        selector=True, hx_target_id='member',
    )

    fieldsets = (FieldSet('group', 'member', 'tags', name=_('Member'), html_id='member'),)

    class Meta:
        model = RedundancyGroupMember
        fields = ('group', 'tags')


class DependencyForm(GenericObjectFormMixin, NetBoxModelForm):
    source = GenericObjectChoiceField(
        label=_('Source (depends on the target)'), content_type_queryset=ContentType.objects.filter(DEPENDENCY_MODELS_Q),
        selector=True, hx_target_id='dependency',
    )
    target = GenericObjectChoiceField(
        label=_('Target (is required)'), content_type_queryset=ContentType.objects.filter(DEPENDENCY_MODELS_Q),
        selector=True, hx_target_id='dependency',
    )

    fieldsets = (FieldSet('source', 'target', 'type', 'criticality', 'comment', 'tags', name=_('Dependency'),
                          html_id='dependency'),)

    class Meta:
        model = Dependency
        fields = ('type', 'criticality', 'comment', 'tags')


# -- import -------------------------------------------------------------------

class BusinessProcessImportForm(NetBoxModelImportForm):
    criticality = CSVChoiceField(choices=CriticalityChoices, required=False)

    class Meta:
        model = BusinessProcess
        fields = ('name', 'criticality', 'rto_hours', 'rpo_hours', 'mtpd_hours', 'nis2_relevant', 'bia_reference',
                  'description', 'comments', 'tags')


class ApplicationImportForm(NetBoxModelImportForm):
    criticality = CSVChoiceField(choices=CriticalityChoices, required=False)

    class Meta:
        model = Application
        fields = ('name', 'vendor', 'criticality', 'description', 'comments', 'tags')


class RedundancyGroupImportForm(NetBoxModelImportForm):
    class Meta:
        model = RedundancyGroup
        fields = ('name', 'min_active', 'description', 'comments', 'tags')


# -- filter forms ---------------------------------------------------------------

class BusinessProcessFilterForm(NetBoxModelFilterSetForm):
    model = BusinessProcess
    criticality = forms.MultipleChoiceField(choices=CriticalityChoices, required=False, label=_('Criticality'))
    nis2_relevant = forms.NullBooleanField(required=False, label=_('NIS2 relevant'),
                                           widget=forms.Select(choices=((None, '---'), (True, _('Yes')), (False, _('No')))))


class ApplicationFilterForm(NetBoxModelFilterSetForm):
    model = Application
    criticality = forms.MultipleChoiceField(choices=CriticalityChoices, required=False, label=_('Criticality'))


class RedundancyGroupFilterForm(NetBoxModelFilterSetForm):
    model = RedundancyGroup


class RedundancyGroupMemberFilterForm(NetBoxModelFilterSetForm):
    model = RedundancyGroupMember
    group_id = DynamicModelMultipleChoiceField(queryset=RedundancyGroup.objects.all(), required=False, label=_('Group'))


class DependencyFilterForm(NetBoxModelFilterSetForm):
    model = Dependency
    type = forms.MultipleChoiceField(choices=DependencyTypeChoices, required=False, label=_('Type'))
    criticality = forms.MultipleChoiceField(choices=CriticalityChoices, required=False, label=_('Criticality'))


# -- analysis -----------------------------------------------------------------------

class ImpactForm(forms.Form):
    scenario = forms.ChoiceField(choices=ScenarioChoices, initial=ScenarioChoices.OUTAGE, label=_('Scenario'))
    device = DynamicModelMultipleChoiceField(queryset=SEED_MODELS['device'].objects.all(), required=False,
                                             label=_('Devices'))
    virtualmachine = DynamicModelMultipleChoiceField(queryset=SEED_MODELS['virtualmachine'].objects.all(),
                                                     required=False, label=_('Virtual machines'))
    cluster = DynamicModelMultipleChoiceField(queryset=SEED_MODELS['cluster'].objects.all(), required=False,
                                              label=_('Clusters'))
    powerpanel = DynamicModelMultipleChoiceField(queryset=SEED_MODELS['powerpanel'].objects.all(), required=False,
                                                 label=_('Power panels'))
    powerfeed = DynamicModelMultipleChoiceField(queryset=SEED_MODELS['powerfeed'].objects.all(), required=False,
                                                label=_('Power feeds'))
    circuit = DynamicModelMultipleChoiceField(queryset=SEED_MODELS['circuit'].objects.all(), required=False,
                                              label=_('Circuits'))
    qdevice_votes = forms.IntegerField(min_value=0, max_value=10, initial=0, required=False,
                                       label=_('QDevice votes per cluster'),
                                       help_text=_('0 = no QDevice (default with 3+ hosts)'))
    no_ha_tag = forms.SlugField(required=False, label=_('Tag for VMs without HA'),
                                help_text=_('Optional, plausibility check only'))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:  # only objects the user may see can be selected
            for field in SEED_MODELS:
                self.fields[field].queryset = self.fields[field].queryset.restrict(user, 'view')


class TreeForm(forms.Form):
    depth = forms.IntegerField(min_value=1, max_value=10, initial=4, required=False, label=_('Maximum depth'))
    cabling = forms.BooleanField(required=False, initial=True, label=_('Show direct cable connections'))
