from django.utils.translation import gettext_lazy as _

from netbox.plugins.navigation import PluginMenu, PluginMenuButton, PluginMenuItem


def _item(model, label):
    return PluginMenuItem(
        link=f'plugins:netbox_dependencies:{model}_list', link_text=label,
        permissions=[f'netbox_dependencies.view_{model}'],
        buttons=(PluginMenuButton(link=f'plugins:netbox_dependencies:{model}_add', title=_('Add'),
                                  icon_class='mdi mdi-plus-thick', permissions=[f'netbox_dependencies.add_{model}']),),
    )


menu = PluginMenu(
    label=_('Dependencies'),
    icon_class='mdi mdi-graph-outline',
    groups=(
        (_('Model'), (
            _item('businessprocess', _('Business processes')),
            _item('application', _('Applications')),
            _item('redundancygroup', _('Redundancy groups')),
            _item('dependency', _('Dependencies')),
        )),
        (_('Analysis'), (
            PluginMenuItem(link='plugins:netbox_dependencies:impact', link_text=_('Impact analysis'),
                           permissions=['netbox_dependencies.view_dependency']),
        )),
    ),
)
