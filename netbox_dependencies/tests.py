import gettext
import os
import re
from types import SimpleNamespace as NS

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import SimpleTestCase, TestCase

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from users.models import User
from utilities.exceptions import AbortRequest

from .engine import DEGRADED, OUTAGE, build_tree, compute_impact, find_cycles, invert
from .graph import endpoints
from .models import Application, BusinessProcess, Dependency, RedundancyGroup, RedundancyGroupMember


def base():
    hosts = ['host-a', 'host-b', 'host-c']
    return dict(
        names={}, feed_panel={'feed1': 'UV1', 'feed2': 'UV2'},
        device_power={'host-a': [['feed1'], ['feed2']], 'host-b': [['feed1'], ['feed2']],
                      'host-c': [['feed1'], ['feed2']], 'sw1': [['feed1']], 'sw2': [['feed2']]},
        device_links={'host-a': ['sw1', 'sw2'], 'host-b': ['sw1', 'sw2'], 'host-c': ['sw1', 'sw2'],
                      'sw1': hosts, 'sw2': hosts},
        cluster_hosts={'cl': hosts},
        vms=[('vm-erp', 'cl', None, False), ('vm-proxy-a', 'cl', 'host-a', True), ('vm-db', 'cl', None, False)],
        groups=[('grp-core', ['sw1', 'sw2'], 1)],
        edges=[('app-erp', 'vm-erp', 'hard'), ('app-erp', 'vm-db', 'hard'), ('app-erp', 'grp-core', 'hard'),
               ('proc', 'app-erp', 'hard'), ('app-backup', 'vm-proxy-a', 'degraded')],
    )


def run(seeds, scenario='outage', **over):
    d = base()
    d.update(over)
    return compute_impact(seeds, scenario=scenario, **d)


class EngineScenarios(SimpleTestCase):
    """The 15 scenarios of the former tests/test_engine.py (v1.0.6), unchanged in substance."""

    def test_01_one_switch(self):
        z, _g, _m = run(['sw1'])
        self.assertEqual((z.get('grp-core'), z.get('app-erp'), z.get('proc')), (DEGRADED,) * 3)
        self.assertNotIn('host-a', z)

    def test_02_both_switches(self):
        z, _g, _m = run(['sw1', 'sw2'])
        self.assertEqual((z['host-a'], z['cl'], z['proc']), (OUTAGE,) * 3)

    def test_03_host_outage(self):
        z, _g, m = run(['host-a'])
        self.assertNotIn('vm-erp', z)
        self.assertEqual((z['vm-proxy-a'], z['app-backup']), (OUTAGE, DEGRADED))
        self.assertNotIn('proc', z)
        self.assertNotIn('cl', z)
        self.assertEqual(len(m), 1)
        self.assertIn('restarted', m[0])
        self.assertIn('Up to 2', m[0])

    def test_04_host_maintenance(self):
        z, _g, m = run(['host-a'], 'maintenance')
        self.assertNotIn('vm-erp', z)
        self.assertEqual(z['vm-proxy-a'], OUTAGE)
        self.assertEqual(len(m), 1)
        self.assertIn('live migration', m[0])

    def test_05_quorum_lost(self):
        z, _g, _m = run(['host-a', 'host-b'])
        self.assertEqual((z['cl'], z['vm-db'], z['proc']), (OUTAGE,) * 3)

    def test_06_one_panel(self):
        z, _g, _m = run(['UV1'])
        self.assertEqual((z['feed1'], z['sw1'], z['grp-core']), (OUTAGE, OUTAGE, DEGRADED))
        self.assertNotIn('host-a', z)

    def test_07_both_panels(self):
        z, _g, _m = run(['UV1', 'UV2'])
        self.assertEqual((z['cl'], z['proc']), (OUTAGE, OUTAGE))

    def test_08_cycle(self):
        e = base()['edges'] + [('p1', 'p2', 'hard'), ('p2', 'p1', 'hard'), ('p1', 'app-erp', 'hard')]
        z, _g, _m = run(['sw1', 'sw2'], edges=e)
        self.assertEqual((z['p1'], z['p2']), (OUTAGE, OUTAGE))
        self.assertTrue(any(set(c) == {'p1', 'p2'} for c in find_cycles(e)))

    def test_09_none_edge(self):
        z, _g, _m = run(['host-a'], edges=[('x', 'vm-proxy-a', 'none')])
        self.assertNotIn('x', z)

    def test_10_qdevice(self):
        two = {'cl': ['host-a', 'host-b']}
        z, _g, _m = run(['host-a'], cluster_hosts=two)
        self.assertEqual(z['cl'], OUTAGE)
        d = base()
        d.update(cluster_hosts=two)
        z, _g, m = compute_impact(['host-a'], scenario='outage', qdevice_votes=1, **d)
        self.assertNotIn('cl', z)
        self.assertNotIn('vm-erp', z)
        self.assertEqual(len(m), 1)

    def test_11_cluster_gone_no_hints(self):
        z, _g, m = run(['host-a', 'host-b'])
        self.assertEqual(m, [])
        self.assertEqual(z['vm-erp'], OUTAGE)

    def test_12_tree(self):
        up = {'esx2': [('grp', 'requires [hard]')], 'esx1': [('grp', 'requires [hard]')],
              'grp': [('sw1', 'member'), ('sw2', 'member')], 'a': [('b', 'x')], 'b': [('a', 'x')]}
        self.assertEqual([(t, k) for t, k, _l, _h in build_tree('esx2', up)], [(1, 'grp'), (2, 'sw1'), (2, 'sw2')])
        self.assertEqual([(t, k) for t, k, _l, _h in build_tree('sw1', invert(up))],
                         [(1, 'grp'), (2, 'esx2'), (2, 'esx1')])
        self.assertEqual(build_tree('a', up)[-1][3], 'cycle')
        self.assertEqual(build_tree('esx2', up, max_depth=1), [(1, 'grp', 'requires [hard]', 'truncated')])

    def test_13_collapsed(self):
        up = {'vm%d' % i: [('cl', 'runs in cluster')] for i in range(5)}
        up['vmx'] = [('cl', 'runs in cluster')]
        up['app'] = [('vmx', 'runs on [hard]')]
        up['cl'] = [('host', 'host')]
        z = build_tree('host', invert(up))
        self.assertEqual([z[0][1], z[1][1], z[2][1]], ['cl', 'vmx', 'app'])
        self.assertEqual((z[3][3], len(z[3][1]), len(z)), ('collapsed', 5, 4))

    def test_14_group_as_source(self):
        d = base()
        d.update(groups=[('grp-core', ['c1', 'c2'], 1), ('grp-dist', ['d1', 'd2'], 1)],
                 edges=[('grp-dist', 'grp-core', 'hard'), ('host', 'grp-dist', 'hard')],
                 cluster_hosts={}, vms=[], device_links={}, device_power={})
        z, _g, _m = compute_impact(['c1', 'c2'], **d)
        self.assertEqual((z['grp-core'], z['grp-dist'], z['host']), (OUTAGE,) * 3)
        z, _g, _m = compute_impact(['c1'], **d)
        self.assertEqual((z['grp-dist'], z['host']), (DEGRADED, DEGRADED))

    def test_15_endpoints(self):
        ct, pp = NS(circuit='inet'), NS(device='patchpanel')
        self.assertEqual(endpoints(NS(connected_endpoints=[NS(device='sw1')], _path=None))[0].device, 'sw1')
        self.assertEqual(endpoints(NS(connected_endpoints=[], _path=NS(path_objects=[['itf'], ['cable'], [ct]]))), [ct])
        self.assertEqual(endpoints(NS(connected_endpoints=[], _path=NS(path_objects=[['itf'], ['cable'], [pp]]))), [])
        self.assertEqual(endpoints(NS(connected_endpoints=None, _path=None)), [])
        self.assertEqual(endpoints(NS(connected_endpoints=[], _path=NS(path_objects=[]))), [])


def grant(user, model, actions, constraints=None):
    """NetBox evaluates permissions via ObjectPermission only (Django user_permissions are ignored)."""
    from django.contrib.contenttypes.models import ContentType
    from users.models import ObjectPermission
    perm = ObjectPermission.objects.create(name=f'test {model.__name__} {actions}', actions=actions,
                                           constraints=constraints)
    perm.object_types.add(ContentType.objects.get_for_model(model))
    perm.users.add(user)


class ModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name='S', slug='s')
        dt = DeviceType.objects.create(manufacturer=Manufacturer.objects.create(name='M', slug='m'), model='T', slug='t')
        role = DeviceRole.objects.create(name='R', slug='r')
        cls.sw1 = Device.objects.create(name='sw1', site=site, device_type=dt, role=role)
        cls.sw2 = Device.objects.create(name='sw2', site=site, device_type=dt, role=role)
        cls.secret = Device.objects.create(name='secret-host', site=site, device_type=dt, role=role)
        cls.app = Application.objects.create(name='ERP')
        cls.proc = BusinessProcess.objects.create(name='Billing', rto_hours=4, mtpd_hours=24, nis2_relevant=True)
        cls.grp = RedundancyGroup.objects.create(name='Core', min_active=1)
        ct = ContentType.objects.get_for_model(Device)
        for sw in (cls.sw1, cls.sw2):
            RedundancyGroupMember.objects.create(group=cls.grp, member_type=ct, member_id=sw.pk)

        def dep(src, tgt, crit='hard', type_='requires'):
            return Dependency.objects.create(source_type=ContentType.objects.get_for_model(src), source_id=src.pk,
                                             target_type=ContentType.objects.get_for_model(tgt), target_id=tgt.pk,
                                             type=type_, criticality=crit)
        dep(cls.proc, cls.app)
        dep(cls.app, cls.grp)
        dep(cls.app, cls.secret)

    def test_rto_mtpd_and_unique_name(self):
        with self.assertRaises(ValidationError):
            BusinessProcess(name='X', rto_hours=48, mtpd_hours=24).full_clean()
        with self.assertRaises(ValidationError):
            Application(name='erp').full_clean()  # case-insensitive unique

    def test_deletion_protection_and_member_cleanup(self):
        with self.assertRaises(AbortRequest), transaction.atomic():  # as NetBox views/API do
            self.secret.delete()
        self.assertTrue(Device.objects.filter(pk=self.secret.pk).exists())
        Dependency.objects.filter(target_id=self.secret.pk).delete()
        self.secret.delete()
        self.sw2.delete()  # member only -> allowed, membership removed
        self.assertEqual(self.grp.members.count(), 1)

    def test_views_and_analysis(self):
        admin = User.objects.create(username='admin_d', is_superuser=True)
        self.client.force_login(admin)
        for url in ('/plugins/dependencies/business-processes/', f'/plugins/dependencies/business-processes/{self.proc.pk}/',
                    '/plugins/dependencies/applications/', '/plugins/dependencies/redundancy-groups/',
                    f'/plugins/dependencies/redundancy-groups/{self.grp.pk}/', '/plugins/dependencies/dependencies/',
                    '/plugins/dependencies/dependencies/add/', '/plugins/dependencies/impact/',
                    f'/plugins/dependencies/tree/dcim/device/{self.sw1.pk}/', self.sw1.get_absolute_url(),
                    '/api/plugins/dependencies/dependencies/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.get(f'/plugins/dependencies/impact/?scenario=outage&device={self.sw1.pk}&device={self.sw2.pk}')
        self.assertContains(r, 'Billing')  # group outage -> app -> process
        self.assertContains(r, 'ERP')
        r = self.client.get(f'/plugins/dependencies/impact/?scenario=outage&device={self.sw1.pk}&export=csv')
        self.assertEqual(r['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(self.client.get('/plugins/dependencies/tree/auth/user/1/').status_code, 404)

    def test_hidden_objects_not_disclosed(self):
        user = User.objects.create(username='limited')
        grant(user, Dependency, ['view'])
        grant(user, Device, ['view'], {'name__startswith': 'sw'})
        self.client.force_login(user)
        # secret-host is a target of ERP; with sw1+sw2 gone, nothing of it may leak
        r = self.client.get(f'/plugins/dependencies/impact/?scenario=outage&device={self.sw1.pk}&device={self.sw2.pk}')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'secret-host')
        self.assertNotContains(r, 'Billing')  # no permission on business processes
        r = self.client.get(f'/plugins/dependencies/tree/netbox_dependencies/application/{self.app.pk}/')
        self.assertEqual(r.status_code, 404)  # no view permission on the start object
        grant(user, Application, ['view'])
        r = self.client.get(f'/plugins/dependencies/tree/netbox_dependencies/application/{self.app.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'secret-host')  # hidden target of ERP
        self.assertContains(r, 'object not visible')

    def test_reasons_mask_hidden_objects(self):
        # ERP is visible, but the redundancy group that caused its outage is not: its name must not leak
        user = User.objects.create(username='reason_user')
        for model in (Dependency, Application, BusinessProcess):
            grant(user, model, ['view'])
        grant(user, Device, ['view'], {'name__startswith': 'sw'})
        self.client.force_login(user)
        url = f'/plugins/dependencies/impact/?scenario=outage&device={self.sw1.pk}&device={self.sw2.pk}'
        for r in (self.client.get(url), self.client.get(url + '&export=csv')):
            self.assertContains(r, 'ERP')
            self.assertNotContains(r, 'Core')
            self.assertContains(r, '(hidden object)')

    def test_panel_hides_invisible_peer(self):
        user = User.objects.create(username='panel_user')
        grant(user, Dependency, ['view'])
        grant(user, RedundancyGroup, ['view'])
        self.client.force_login(user)
        grp_page = self.client.get(self.grp.get_absolute_url())
        self.assertEqual(grp_page.status_code, 200)
        # a device page as seen by a user who can view the device but not the application that requires it
        grant(user, Device, ['view'])
        r = self.client.get(self.secret.get_absolute_url())
        self.assertNotContains(r, '>ERP<')
        self.assertContains(r, 'not shown')

    def test_csv_injection_neutralised(self):
        from .views import csv_safe
        self.assertEqual(csv_safe('=HYPERLINK("x")'), "'=HYPERLINK(\"x\")")
        self.assertEqual(csv_safe('normal'), 'normal')

    def test_api_create_dependency_validates_objects(self):
        admin = User.objects.create(username='admin_api', is_superuser=True)
        self.client.force_login(admin)
        r = self.client.post('/api/plugins/dependencies/dependencies/', {
            'source_type': 'dcim.device', 'source_id': 999999, 'target_type': 'dcim.device',
            'target_id': self.sw1.pk, 'type': 'requires'}, content_type='application/json')
        self.assertEqual(r.status_code, 400)
        # a user who cannot view sw1 gets the same answer as for a non-existing object
        user = User.objects.create(username='api_limited')
        grant(user, Dependency, ['add', 'view'])
        grant(user, Device, ['view'], {'name': 'sw2'})
        self.client.force_login(user)
        r = self.client.post('/api/plugins/dependencies/dependencies/', {
            'source_type': 'dcim.device', 'source_id': self.sw2.pk, 'target_type': 'dcim.device',
            'target_id': self.sw1.pk, 'type': 'requires'}, content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('target_id', r.json())


class TranslationTests(TestCase):
    def test_compiled_catalog_is_current(self):
        """django.mo is shipped (target systems usually lack gettext) - it must contain every translated msgid."""
        base_dir = os.path.join(os.path.dirname(__file__), 'locale', 'de', 'LC_MESSAGES')
        po = open(os.path.join(base_dir, 'django.po'), encoding='utf-8').read()
        with open(os.path.join(base_dir, 'django.mo'), 'rb') as f:
            catalog = gettext.GNUTranslations(f)._catalog
        missing = [m for m in re.findall(r'^msgid "(.+)"\nmsgstr "(?!")', po, re.M)
                   if m.replace('\\"', '"') not in catalog]
        self.assertEqual(missing, [], 'django.mo is outdated - run makemessages/msgfmt (see CLAUDE.md)')
        self.assertEqual(re.findall(r'^#, .*fuzzy.*\n(?:#\|.*\n)*msgid "(.*)"', po, re.M), [], 'fuzzy (guessed) translations - fix them')
