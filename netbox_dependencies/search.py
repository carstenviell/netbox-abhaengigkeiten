from netbox.search import SearchIndex, register_search

from .models import Application, BusinessProcess, RedundancyGroup


@register_search
class BusinessProcessIndex(SearchIndex):
    model = BusinessProcess
    fields = (('name', 100), ('description', 500), ('bia_reference', 300))
    display_attrs = ('criticality', 'description')


@register_search
class ApplicationIndex(SearchIndex):
    model = Application
    fields = (('name', 100), ('vendor', 300), ('description', 500))
    display_attrs = ('vendor', 'criticality', 'description')


@register_search
class RedundancyGroupIndex(SearchIndex):
    model = RedundancyGroup
    fields = (('name', 100), ('description', 500))
    display_attrs = ('min_active', 'description')
