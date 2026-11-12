"""
Query-parameter handling shared by every list endpoint.

Two problems this solves, both of which bit this codebase.

**Unknown parameters are rejected, not ignored.** django-filter silently drops
a query parameter it has not declared, so `?prn=220200921` against an endpoint
without a `prn` filter returns the whole table. Measured 2026-09-30: a
three-row roster answered `?prn=999999999` -- a PRN belonging to nobody -- with
all three rows. A reconciliation script reading `count > 0` as "found" matches
the wrong student. It fails open, silently, and the output looks plausible.

**Human keys are normalised on the way in.** PRN is stored canonically, but a
filter value is never saved, so `" 220200921 "` pasted from a spreadsheet would
miss every row. Filter input is trimmed and upper-cased on the same path as
write input.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

#: Parameters every list endpoint accepts regardless of its filterset.
ALWAYS_ALLOWED = frozenset(
    {"page", "page_size", "ordering", "search", "format", "cursor", "limit", "offset"}
)


class RejectUnknownQueryParams(BaseFilterBackend):
    """
    Answer 400 for a query parameter the endpoint does not understand.

    A typo'd `?pm=220200921` must not quietly return everything. Install it
    ahead of the other backends so it runs before any filtering happens.
    """

    def filter_queryset(self, request, queryset, view):
        allowed = set(ALWAYS_ALLOWED)

        filterset_class = getattr(view, "filterset_class", None)
        if filterset_class is not None:
            allowed |= set(filterset_class.base_filters)
        allowed |= set(getattr(view, "filterset_fields", None) or ())

        unknown = sorted(set(request.query_params) - allowed)
        if unknown:
            raise ValidationError(
                {
                    param: (
                        "Unrecognised query parameter. This endpoint accepts: "
                        + ", ".join(sorted(allowed))
                        + "."
                    )
                    for param in unknown
                }
            )
        return queryset


def normalise_human_key(value: str) -> str:
    """Trim and upper-case, matching how human keys are stored."""
    return (value or "").strip().upper()


class HumanKeyFilter(filters.CharFilter):
    """Exact match on a stored-canonical identifier, tolerant of paste noise."""

    def filter(self, queryset, value):
        cleaned = normalise_human_key(value)
        if not cleaned:
            return queryset
        return self.get_method(queryset)(**{f"{self.field_name}__exact": cleaned})


class HumanKeyInFilter(filters.CharFilter):
    """
    Batch match: `?prns=220200921,220200922`.

    Capped, because reconciling a spreadsheet one request at a time is
    unusable but an uncapped IN clause is a denial-of-service shaped hole.
    """

    MAX_VALUES = 200

    def filter(self, queryset, value):
        if not value:
            return queryset
        keys = [normalise_human_key(part) for part in value.split(",")]
        keys = [key for key in keys if key]
        if not keys:
            return queryset
        if len(keys) > self.MAX_VALUES:
            raise ValidationError(
                {
                    self.field_name: (
                        f"At most {self.MAX_VALUES} values per request; "
                        f"received {len(keys)}."
                    )
                }
            )
        return self.get_method(queryset)(**{f"{self.field_name}__in": keys})


class ReportUnmatchedPrnsMixin:
    """
    Add `unmatched_prns` to a paginated list when `?prns=` was sent.

    Set `prn_field` to the PRN's ORM path ("prn", "student__prn"). A requested
    PRN counts as missed if it is not in the whole filtered set, so a company
    asking for a hidden student sees it listed -- same as an absent one.
    """

    prn_field = "prn"

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        raw = self.request.query_params.get("prns")
        if raw:
            asked = list(
                dict.fromkeys(
                    key for key in (normalise_human_key(p) for p in raw.split(",")) if key
                )
            )
            # Whole filtered queryset, not one page, or a 400-row lookup would
            # report false misses. If this is slow, cap it at the 200-key limit.
            found = set(
                self.filter_queryset(self.get_queryset())
                .filter(**{f"{self.prn_field}__in": asked})
                .values_list(self.prn_field, flat=True)
            )
            response.data["unmatched_prns"] = [key for key in asked if key not in found]
        return response
