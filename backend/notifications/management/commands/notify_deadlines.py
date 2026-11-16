"""Send `deadline_soon` notifications. Safe to run on a schedule: it never repeats one."""

from django.core.management.base import BaseCommand

from notifications.services import notify_deadlines


class Command(BaseCommand):
    help = "Notify eligible students who have not applied that a posting's deadline is close."

    def handle(self, *args, **options):
        sent = notify_deadlines()
        self.stdout.write(f"{sent} deadline notification(s) sent.")
