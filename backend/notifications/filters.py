from django_filters import rest_framework as filters

from notifications.models import Notification


class NotificationFilter(filters.FilterSet):
    unread = filters.BooleanFilter(method="filter_unread")

    class Meta:
        model = Notification
        fields = ["unread"]

    def filter_unread(self, queryset, name, value):
        return queryset.filter(read_at__isnull=value is True)
