from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from .choices import CriticalityChoices, DependencyTypeChoices, DEPENDENCY_MODELS_Q, GROUP_MEMBER_MODELS_Q


class _Named(NetBoxModel):
    name = models.CharField(verbose_name=_('name'), max_length=100)
    description = models.CharField(verbose_name=_('description'), max_length=200, blank=True)
    comments = models.TextField(verbose_name=_('comments'), blank=True)

    class Meta:
        abstract = True
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse(f'plugins:netbox_dependencies:{self._meta.model_name}', args=[self.pk])


class BusinessProcess(_Named):
    owner = models.ForeignKey(
        'tenancy.Contact', verbose_name=_('process owner'), on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
    )
    criticality = models.CharField(verbose_name=_('criticality'), max_length=20, choices=CriticalityChoices,
                                   blank=True)
    rto_hours = models.PositiveIntegerField(verbose_name=_('RTO (hours)'), null=True, blank=True,
                                            help_text=_('Recovery time objective'))
    rpo_hours = models.PositiveIntegerField(verbose_name=_('RPO (hours)'), null=True, blank=True,
                                            help_text=_('Recovery point objective'))
    mtpd_hours = models.PositiveIntegerField(verbose_name=_('MTPD (hours)'), null=True, blank=True,
                                             help_text=_('Maximum tolerable period of disruption'))
    nis2_relevant = models.BooleanField(verbose_name=_('NIS2 relevant'), default=False)
    bia_reference = models.CharField(verbose_name=_('BIA reference'), max_length=200, blank=True,
                                     help_text=_('Reference to the business impact analysis (BCM)'))

    class Meta(_Named.Meta):
        verbose_name = _('business process')
        verbose_name_plural = _('business processes')
        constraints = (models.UniqueConstraint(Lower('name'), name='%(app_label)s_businessprocess_name'),)

    def clean(self):
        super().clean()
        if self.rto_hours is not None and self.mtpd_hours is not None and self.rto_hours > self.mtpd_hours:
            raise ValidationError({'rto_hours': _('RTO must not exceed MTPD.')})

    def get_criticality_color(self):
        return CriticalityChoices.colors.get(self.criticality)


class Application(_Named):
    vendor = models.CharField(verbose_name=_('vendor'), max_length=100, blank=True)
    owner = models.ForeignKey(
        'tenancy.Contact', verbose_name=_('application owner'), on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
    )
    criticality = models.CharField(verbose_name=_('criticality'), max_length=20, choices=CriticalityChoices,
                                   blank=True)

    class Meta(_Named.Meta):
        verbose_name = _('application')
        verbose_name_plural = _('applications')
        constraints = (models.UniqueConstraint(Lower('name'), name='%(app_label)s_application_name'),)

    def get_criticality_color(self):
        return CriticalityChoices.colors.get(self.criticality)


class RedundancyGroup(_Named):
    min_active = models.PositiveIntegerField(
        verbose_name=_('minimum active'), default=1, validators=[MinValueValidator(1)],
        help_text=_('Fewer available members than this means an outage of the group'),
    )

    class Meta(_Named.Meta):
        verbose_name = _('redundancy group')
        verbose_name_plural = _('redundancy groups')
        constraints = (models.UniqueConstraint(Lower('name'), name='%(app_label)s_redundancygroup_name'),)


class RedundancyGroupMember(NetBoxModel):
    group = models.ForeignKey(RedundancyGroup, verbose_name=_('group'), on_delete=models.CASCADE,
                              related_name='members')
    member_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name='+',
                                    limit_choices_to=GROUP_MEMBER_MODELS_Q)
    member_id = models.PositiveBigIntegerField()
    member = GenericForeignKey('member_type', 'member_id')

    class Meta:
        ordering = ('group', 'member_type', 'member_id')
        verbose_name = _('redundancy group member')
        verbose_name_plural = _('redundancy group members')
        constraints = (models.UniqueConstraint(fields=('group', 'member_type', 'member_id'),
                                               name='%(app_label)s_groupmember_unique'),)
        indexes = (models.Index(fields=('member_type', 'member_id')),)

    def __str__(self):
        return f'{self.group}: {self.member}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_dependencies:redundancygroupmember', args=[self.pk])


class Dependency(NetBoxModel):
    """source depends on target (source -> target)."""
    source_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name='+',
                                    limit_choices_to=DEPENDENCY_MODELS_Q)
    source_id = models.PositiveBigIntegerField()
    source = GenericForeignKey('source_type', 'source_id')
    target_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name='+',
                                    limit_choices_to=DEPENDENCY_MODELS_Q)
    target_id = models.PositiveBigIntegerField()
    target = GenericForeignKey('target_type', 'target_id')
    type = models.CharField(verbose_name=_('type'), max_length=30, choices=DependencyTypeChoices)
    criticality = models.CharField(verbose_name=_('criticality'), max_length=20, choices=CriticalityChoices,
                                   default=CriticalityChoices.HARD)
    comment = models.CharField(verbose_name=_('comment'), max_length=200, blank=True)

    class Meta:
        ordering = ('source_type', 'source_id', 'target_type', 'target_id')
        verbose_name = _('dependency')
        verbose_name_plural = _('dependencies')
        constraints = (models.UniqueConstraint(fields=('source_type', 'source_id', 'target_type', 'target_id', 'type'),
                                               name='%(app_label)s_dependency_unique'),)
        indexes = (models.Index(fields=('source_type', 'source_id')), models.Index(fields=('target_type', 'target_id')))

    def __str__(self):
        return f'{self.source} → {self.target}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_dependencies:dependency', args=[self.pk])

    def clean(self):
        super().clean()
        if self.source_type_id and self.target_type_id and \
                (self.source_type_id, self.source_id) == (self.target_type_id, self.target_id):
            raise ValidationError(_('An object cannot depend on itself.'))

    def get_criticality_color(self):
        return CriticalityChoices.colors.get(self.criticality)
