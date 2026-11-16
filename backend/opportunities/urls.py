from rest_framework.routers import SimpleRouter

from opportunities import views

# Applications first: the postings router has an empty prefix, whose detail
# route would otherwise swallow "applications/" as an opportunity id.
router = SimpleRouter(trailing_slash=False)
router.register("applications", views.ApplicationViewSet, basename="application")
router.register("", views.OpportunityViewSet, basename="opportunity")

urlpatterns = router.urls
