from netbox.api.routers import NetBoxRouter

from . import views

app_name = 'netbox_dependencies-api'

router = NetBoxRouter()
router.register('business-processes', views.BusinessProcessViewSet)
router.register('applications', views.ApplicationViewSet)
router.register('redundancy-groups', views.RedundancyGroupViewSet)
router.register('redundancy-group-members', views.RedundancyGroupMemberViewSet)
router.register('dependencies', views.DependencyViewSet)
urlpatterns = router.urls
