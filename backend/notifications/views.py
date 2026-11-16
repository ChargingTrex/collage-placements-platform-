from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from notifications.filters import NotificationFilter
from notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    opportunity = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "kind", "opportunity", "created_at", "read_at"]
        read_only_fields = fields

    def get_opportunity(self, notification):
        return {"id": notification.opportunity_id, "title": notification.opportunity.title}


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Your own notifications only; another user's id is a 404."""

    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).select_related("opportunity")

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="read-all", url_name="read-all")
    def read_all(self, request):
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)
