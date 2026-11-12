"""The portal's published signing keys."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.identity import jwks


@api_view(["GET"])
@permission_classes([AllowAny])
def jwks_view(request):
    """
    Public keys, so anything holding a token can verify it without being given
    a key. Unauthenticated by definition -- a JWKS that needs a credential to
    read is useless to the thing trying to establish one.

    Both halves of a rotation appear here at once, which is the whole point:
    during a rotation tokens signed by either key must verify.
    """
    return Response(jwks())
