"""Request shapes for the JD match endpoints, and the category list."""

from rest_framework import serializers

from matching.models import RoleCategory
from matching.vectorstore import FILTER_FIELDS

#: Long enough to say what a role needs; short enough to embed and read.
JD_MIN_CHARS = 30
JD_MAX_CHARS = 20_000
MAX_K = 50
MAX_STUDENT_IDS = 200
#: A filter narrows a search; a longer list is a request to do work, not a
#: filter. Each value costs a comparison per candidate (and, for categories,
#: a name lookup), so both are bounded before any of it runs.
MAX_FILTER_VALUES = 20
MAX_FILTER_VALUE_CHARS = 100
_OPERATORS = {"in", "gte", "lte"}


class JobDescriptionSerializer(serializers.Serializer):
    jd_text = serializers.CharField(min_length=JD_MIN_CHARS, max_length=JD_MAX_CHARS, trim_whitespace=True)


def _scalar(value) -> bool:
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def _too_long(value) -> bool:
    return isinstance(value, str) and len(value) > MAX_FILTER_VALUE_CHARS


class MatchFiltersField(serializers.DictField):
    """
    The vector store's filter dialect, and only its fields.

    An unknown key is a 400, never ignored: a typo'd filter that silently
    matched everyone is the same failure as an undeclared query parameter.
    """

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object of filters.")
        errors = {}
        for key, condition in data.items():
            if key not in FILTER_FIELDS:
                errors[key] = f"Unknown filter. Use one of: {', '.join(FILTER_FIELDS)}."
            elif isinstance(condition, dict):
                unknown = set(condition) - _OPERATORS
                if unknown or not condition:
                    errors[key] = "Use {'in': [...]}, {'gte': n} or {'lte': n}."
                elif "in" in condition and not (
                    isinstance(condition["in"], list) and all(_scalar(v) for v in condition["in"])
                ):
                    errors[key] = "'in' takes a list of values."
                elif "in" in condition and len(condition["in"]) > MAX_FILTER_VALUES:
                    errors[key] = f"'in' takes at most {MAX_FILTER_VALUES} values."
                elif "in" in condition and any(_too_long(v) for v in condition["in"]):
                    errors[key] = f"Each value is at most {MAX_FILTER_VALUE_CHARS} characters."
                elif any(not _scalar(condition[op]) for op in ("gte", "lte") if op in condition):
                    errors[key] = "'gte' and 'lte' take a number."
                elif any(_too_long(condition[op]) for op in ("gte", "lte") if op in condition):
                    errors[key] = f"Each value is at most {MAX_FILTER_VALUE_CHARS} characters."
            elif not _scalar(condition):
                errors[key] = "Use a value, or {'in': [...]}, {'gte': n}, {'lte': n}."
            elif _too_long(condition):
                errors[key] = f"Each value is at most {MAX_FILTER_VALUE_CHARS} characters."
        if errors:
            raise serializers.ValidationError(errors)
        return dict(data)


class MatchSearchSerializer(JobDescriptionSerializer):
    k = serializers.IntegerField(min_value=1, max_value=MAX_K, default=20)
    filters = MatchFiltersField(required=False, default=dict)


class MatchScoreSerializer(JobDescriptionSerializer):
    student_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=MAX_STUDENT_IDS, allow_empty=True
    )


class RoleCategorySerializer(serializers.ModelSerializer):
    """What anyone signed in may see of a category: no centroid, no aliases."""

    top_skills = serializers.SerializerMethodField()

    class Meta:
        model = RoleCategory
        fields = ("name", "jd_count", "top_skills")

    def get_top_skills(self, category) -> list[str]:
        return category.top_skills()
