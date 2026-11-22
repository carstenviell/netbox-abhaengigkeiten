from django.urls import include, path

from utilities.urls import get_model_urls

from . import views

app_name = 'netbox_dependencies'

urlpatterns = [
    path('impact/', views.ImpactView.as_view(), name='impact'),
    path('tree/<str:app_label>/<str:model>/<int:pk>/', views.TreeView.as_view(), name='tree'),
]
for prefix, model in (('business-processes', 'businessprocess'), ('applications', 'application'),
                      ('redundancy-groups', 'redundancygroup'), ('redundancy-group-members', 'redundancygroupmember'),
                      ('dependencies', 'dependency')):
    urlpatterns += [
        path(f'{prefix}/', include(get_model_urls('netbox_dependencies', model, detail=False))),
        path(f'{prefix}/<int:pk>/', include(get_model_urls('netbox_dependencies', model))),
    ]
