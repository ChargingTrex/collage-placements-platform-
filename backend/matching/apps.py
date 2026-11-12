from django.apps import AppConfig


class MatchingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "matching"

    def ready(self):
        from matching import signals  # noqa: F401  connects the skill-graph cache
