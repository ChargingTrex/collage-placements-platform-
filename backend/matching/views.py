"""
JD match endpoints for companies and admins.

    POST /api/matching/search   {jd_text, k, filters}  the k best visible matches
    POST /api/matching/score    {jd_text, student_ids}  named visible profiles
    GET  /api/matching/categories                       the role categories (any role)

A result is the company-facing profile (the same serializer as
/api/profiles/students) plus the match breakdown. Age, DOB, the resume's
CGPA and verification flags are never in it. Both endpoints return a
ranked top-k, not a page: `k` is capped at `serializers.MAX_K`.
"""

from __future__ import annotations

from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCompanyOrAdmin
from matching.models import RoleCategory
from matching.serializers import MatchScoreSerializer, MatchSearchSerializer, RoleCategorySerializer
from matching.throttling import MatchingThrottle
from profiles import match
from profiles.serializers import CompanyProfileSerializer


def _results(scored, request) -> list[dict]:
    return [
        {
            **CompanyProfileSerializer(profile, context={"request": request}).data,
            "categories": match.profile_categories(profile),
            "match": score.as_dict(),
        }
        for profile, score in scored
    ]


class MatchSearchView(APIView):
    permission_classes = [IsCompanyOrAdmin]
    throttle_classes = [MatchingThrottle]

    def post(self, request):
        serializer = MatchSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        job = match.read_job(data["jd_text"], record=True)
        scored, fallback = match.search(request.user, job, data["k"], data["filters"])
        return Response(
            {
                "count": len(scored),
                "fallback": fallback,
                "job": job.summary(),
                "results": _results(scored, request),
            }
        )


class MatchScoreView(APIView):
    permission_classes = [IsCompanyOrAdmin]
    throttle_classes = [MatchingThrottle]

    def post(self, request):
        serializer = MatchScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        job = match.read_job(data["jd_text"], record=True)
        scored = match.score_named(request.user, job, data["student_ids"])
        return Response({"count": len(scored), "job": job.summary(), "results": _results(scored, request)})


class RoleCategoryListView(ListAPIView):
    """
    The roles recruiters' JDs describe, most-posted first. Empty until a JD
    has been read with the LLM on: categories are never invented.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RoleCategorySerializer
    queryset = RoleCategory.objects.all()
