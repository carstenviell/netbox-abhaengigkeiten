from netbox.plugins import PluginConfig


class DependenciesConfig(PluginConfig):
    name = 'netbox_dependencies'
    verbose_name = 'Dependencies'
    description = ('Document dependencies (business process -> application -> VM -> cluster/host -> network '
                   '-> power) and analyse the impact of outages and maintenance.')
    version = '2.0.0'
    author = 'Carsten Viell'
    base_url = 'dependencies'
    min_version = '4.7.0'
    default_settings = {}

    def ready(self):
        super().ready()
        from . import signals  # noqa: F401  (deletion protection)


config = DependenciesConfig
