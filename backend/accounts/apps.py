from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        """
        Install the multi-key token backend.

        SimpleJWT 5.4 removed the TOKEN_BACKEND_CLASS setting, and its Token
        class resolves its backend once into `_token_backend`. Filling that
        slot here is the remaining seam, and it has to happen before any token
        is minted -- hence app ready rather than first use.
        """
        from rest_framework_simplejwt.tokens import Token

        from accounts.identity import MultiKeyTokenBackend
        from django.conf import settings

        jwt = settings.SIMPLE_JWT
        Token._token_backend = MultiKeyTokenBackend(
            algorithm=jwt["ALGORITHM"],
            signing_key=None,      # resolved per call from the keyring
            verifying_key=None,    # resolved per token by its kid
            audience=jwt.get("AUDIENCE"),
            issuer=jwt.get("ISSUER"),
        )
