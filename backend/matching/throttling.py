"""
One per-user budget for every endpoint that may call the LLM or score a pool.

Match search, scoring, a student's own match and resume analysis each cost a
model call (or a pass over hundreds of profiles), so they share the
`"matching"` scope in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`.
"""

from rest_framework.settings import api_settings
from rest_framework.throttling import UserRateThrottle


class MatchingThrottle(UserRateThrottle):
    scope = "matching"

    def get_rate(self):
        # Read per request, not frozen at import as DRF's class attribute
        # is, so a changed setting (or a test's) takes effect.
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)
