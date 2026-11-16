"""The per-user budget for the shortlist exports (CV zip, contact zip)."""

from rest_framework.settings import api_settings
from rest_framework.throttling import UserRateThrottle


class ExportThrottle(UserRateThrottle):
    scope = "export"

    def get_rate(self):
        # Read per request so a changed setting (or a test's) takes effect.
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)
