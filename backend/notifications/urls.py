from rest_framework.routers import SimpleRouter

from notifications import views

router = SimpleRouter(trailing_slash=False)
router.register("", views.NotificationViewSet, basename="notification")

urlpatterns = router.urls
