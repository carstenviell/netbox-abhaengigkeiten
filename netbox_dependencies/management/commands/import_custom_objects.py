"""
Import the data of netbox-abhaengigkeiten 1.x (NetBox Labs Custom Objects) into the plugin models.

Dry run by default; writes only with --commit. Idempotent: existing objects (by name, or by
source/target/type for dependencies) are kept, never overwritten. The custom objects themselves
are not modified or deleted.
"""
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...choices import DEPENDENCY_MODELS, GROUP_MEMBER_MODELS
from ...models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember

CRITICALITY = {'hart': 'hard', 'degradiert': 'degraded', 'keine': 'none'}
TYPE = {'laeuft_auf': 'runs_on', 'benoetigt': 'requires', 'authentifiziert_ueber': 'authenticates_via',
        'daten_von': 'data_from', 'strom_klima': 'power_cooling'}
ALLOWED = {f'{a}.{m}' for a, m in DEPENDENCY_MODELS}
MEMBERS = {f'{a}.{m}' for a, m in GROUP_MEMBER_MODELS}


class Rollback(Exception):
    pass


class Command(BaseCommand):
    help = 'Import netbox-abhaengigkeiten 1.x custom objects into netbox-dependencies (dry run unless --commit).'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true', help='Write the changes (default: dry run).')

    def handle(self, *args, commit=False, **options):
        if not apps.is_installed('netbox_custom_objects'):
            raise CommandError('netbox_custom_objects is not installed - nothing to import.')
        from netbox_custom_objects.models import CustomObjectType

        def cot(name):
            try:
                return CustomObjectType.objects.get(name=name).get_model()
            except CustomObjectType.DoesNotExist:
                raise CommandError(f'Custom object type "{name}" not found.')

        self.mapped = {}  # (label, pk) of a custom object -> plugin object
        self.counts = {}
        try:
            with transaction.atomic():
                self.import_named(cot('geschaeftsprozess'), BusinessProcess, lambda o: dict(
                    owner=getattr(o, 'verantwortlicher', None), criticality=CRITICALITY.get(o.kritikalitaet or '', ''),
                    rto_hours=o.rto_h, rpo_hours=o.rpo_h, mtpd_hours=o.mtpd_h, nis2_relevant=bool(o.nis2_relevant),
                    bia_reference=o.bia_referenz or ''))
                self.import_named(cot('applikation'), Application, lambda o: dict(
                    vendor=o.hersteller or '', owner=getattr(o, 'fachverantwortlicher', None),
                    criticality=CRITICALITY.get(o.kritikalitaet or '', '')))
                groups = self.import_named(cot('redundanzgruppe'), RedundancyGroup,
                                           lambda o: dict(min_active=o.min_aktiv or 1))
                for old, new in groups:
                    for m in old.mitglieder.all():
                        if m._meta.label_lower not in MEMBERS:
                            self.warn(f'{old}: member type {m._meta.label_lower} not supported, skipped')
                            continue
                        _obj, created = RedundancyGroupMember.objects.get_or_create(
                            group=new, member_type=ContentType.objects.get_for_model(m), member_id=m.pk)
                        self.count('redundancy group members', created)
                for e in cot('abhaengigkeit').objects.all():
                    source, target = self.resolve(e.quelle), self.resolve(e.ziel)
                    if source is None or target is None:
                        self.warn(f'dependency {e.pk}: source/target missing or not supported, skipped')
                        continue
                    dep_type = TYPE.get(e.typ or '')
                    if dep_type is None:
                        self.warn(f'dependency {e.pk}: unknown type "{e.typ}", skipped')
                        continue
                    _obj, created = Dependency.objects.get_or_create(
                        source_type=ContentType.objects.get_for_model(source), source_id=source.pk,
                        target_type=ContentType.objects.get_for_model(target), target_id=target.pk, type=dep_type,
                        defaults={'criticality': CRITICALITY.get(e.kritikalitaet or '', 'hard'),
                                  'comment': (getattr(e, 'bemerkung', '') or '')[:200]})
                    self.count('dependencies', created)
                if not commit:
                    raise Rollback
        except Rollback:
            pass
        for name, (new, existing) in self.counts.items():
            self.stdout.write(f'{name}: {new} new, {existing} already present')
        self.stdout.write(self.style.SUCCESS('Committed.') if commit else
                          self.style.WARNING('Dry run - nothing written. Use --commit to import.'))

    def count(self, name, created):
        new, existing = self.counts.get(name, (0, 0))
        self.counts[name] = (new + 1, existing) if created else (new, existing + 1)

    def warn(self, text):
        self.stdout.write(self.style.WARNING(text))

    def import_named(self, old_model, new_model, fields):
        pairs = []
        for old in old_model.objects.all():
            new = new_model.objects.filter(name__iexact=old.name).first()
            created = new is None
            if created:
                new = new_model(name=old.name, **fields(old))
                new.full_clean()
                new.save()
            self.mapped[(old._meta.label_lower, old.pk)] = new
            self.count(str(new_model._meta.verbose_name_plural), created)
            pairs.append((old, new))
        return pairs

    def resolve(self, obj):
        if obj is None:
            return None
        mapped = self.mapped.get((obj._meta.label_lower, obj.pk))
        if mapped is not None:
            return mapped
        return obj if obj._meta.label_lower in ALLOWED else None
