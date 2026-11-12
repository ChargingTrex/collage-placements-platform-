from __future__ import annotations

from rest_framework import serializers

from roster.models import FlaggedSignup, Student


class StudentSerializer(serializers.ModelSerializer):
    has_account = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            "id",
            "prn",
            "email",
            "full_name",
            "department",
            "batch",
            "cgpa",
            "phone",
            "is_placement_eligible",
            "has_account",
            "created_at",
        )
        read_only_fields = ("id", "has_account", "created_at")

    def get_has_account(self, student: Student) -> bool:
        # Annotated by the viewset to keep this off the N+1 path.
        return bool(getattr(student, "account_exists", False))


class FlaggedSignupSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    reviewed_by_email = serializers.CharField(
        source="reviewed_by.email", read_only=True, default=None
    )

    class Meta:
        model = FlaggedSignup
        fields = (
            "id",
            "prn",
            "email",
            "reason",
            "reason_display",
            "attempts",
            "status",
            "admin_note",
            "reviewed_by_email",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FlaggedSignupReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[FlaggedSignup.Status.RESOLVED, FlaggedSignup.Status.DISMISSED]
    )
    admin_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class RosterUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    dry_run = serializers.BooleanField(
        default=False,
        help_text="Validate and report without writing anything.",
    )

    def validate_file(self, upload):
        if not upload.name.lower().endswith(".csv"):
            raise serializers.ValidationError("Upload a .csv file.")
        return upload
