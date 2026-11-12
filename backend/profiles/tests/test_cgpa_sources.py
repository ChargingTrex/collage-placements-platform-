"""
Every CGPA on record, kept apart, and which of them disagree.

The student stating a CGPA is a claim, not an answer: it is stored beside the
roster's figure, the one printed on the transcript and the one recomputed from
the semesters, and the placement cell decides. Nothing here overwrites
anything.
"""

import pytest
from django.urls import reverse

from profiles.models import StudentProfile
from profiles.verification import cgpa_sources

pytestmark = pytest.mark.django_db


def set_cgpas(profile, **values):
    StudentProfile.objects.filter(pk=profile.pk).update(**values)
    profile.refresh_from_db()
    return profile


class TestSources:
    def test_all_four_are_reported_apart(self, profile):
        set_cgpas(
            profile, parsed_cgpa="8.40", recomputed_cgpa="8.41", confirmed_cgpa="8.40"
        )

        values = cgpa_sources(profile)["values"]

        assert values["roster"] == 8.72  # the make_student default
        assert values["transcript_printed"] == 8.40
        assert values["transcript_recomputed"] == 8.41
        assert values["student"] == 8.40

    def test_a_source_with_no_value_is_none_not_zero(self, profile):
        """Zero is a CGPA; absent is not."""
        values = cgpa_sources(profile)["values"]

        assert values["transcript_printed"] is None
        assert values["student"] is None

    def test_sources_within_tolerance_do_not_disagree(self, profile):
        set_cgpas(profile, parsed_cgpa="8.72", confirmed_cgpa="8.72")

        assert cgpa_sources(profile)["disagreements"] == []

    def test_a_student_claim_that_differs_is_flagged(self, profile):
        set_cgpas(profile, confirmed_cgpa="9.90")  # roster says 8.72

        disagreements = cgpa_sources(profile)["disagreements"]

        assert len(disagreements) == 1
        assert set(disagreements[0]["sources"]) == {"roster", "student"}
        assert "9.9" in disagreements[0]["message"]

    def test_a_tampered_transcript_still_disagrees_with_its_own_recomputation(self, profile):
        set_cgpas(profile, parsed_cgpa="9.50", recomputed_cgpa="8.72")

        pairs = [set(d["sources"]) for d in cgpa_sources(profile)["disagreements"]]

        assert {"transcript_printed", "transcript_recomputed"} in pairs

    def test_every_disagreeing_pair_is_named(self, profile):
        set_cgpas(profile, parsed_cgpa="5.00", recomputed_cgpa="6.00", confirmed_cgpa="7.00")

        disagreements = cgpa_sources(profile)["disagreements"]

        # Four sources that all differ: every one of the six pairs.
        assert len(disagreements) == 6

    def test_a_student_with_no_resume_still_gets_the_comparison(self, profile):
        """
        The regression this helper exists for.

        `verification_checks` returns nothing until a resume has been read, so
        routing the CGPA comparison through it would hide a disagreement for
        any student who has not uploaded one.
        """
        assert not profile.resume
        set_cgpas(profile, confirmed_cgpa="9.90")

        assert cgpa_sources(profile)["disagreements"]


class TestAdminSeesIt:
    def test_the_admin_detail_payload_carries_the_sources(self, admin_client, profile):
        set_cgpas(profile, confirmed_cgpa="9.90")

        body = admin_client.get(
            reverse("admin-profile-detail", args=[profile.student_id])
        ).json()

        assert body["cgpa_sources"]["values"]["student"] == 9.90
        assert body["cgpa_sources"]["disagreements"]

    def test_the_student_payload_does_not_carry_them(self, as_student):
        """The comparison is the placement cell's view, not the student's."""
        body = as_student.get(reverse("my-profile")).json()

        assert "cgpa_sources" not in body

    def test_the_company_payload_does_not_carry_them(self, as_company):
        body = as_company.get(reverse("company-profile-list")).json()

        assert "cgpa_sources" not in str(body)


class TestStudentStatesTheirCgpa:
    def test_it_can_be_stated_with_no_transcript_uploaded(self, as_student, profile):
        """The CGPA entry and the transcript upload are two separate steps."""
        response = as_student.post(
            reverse("my-confirm-cgpa"), {"cgpa": "8.50"}, format="json"
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert str(profile.confirmed_cgpa) == "8.50"

    def test_it_never_overwrites_the_roster_figure(self, as_student, profile):
        as_student.post(reverse("my-confirm-cgpa"), {"cgpa": "9.90"}, format="json")

        profile.refresh_from_db()
        assert str(profile.student.cgpa) == "8.72"

    def test_it_never_overwrites_what_the_transcript_said(self, as_student, profile):
        set_cgpas(profile, parsed_cgpa="8.40", recomputed_cgpa="8.41")

        as_student.post(reverse("my-confirm-cgpa"), {"cgpa": "9.90"}, format="json")

        profile.refresh_from_db()
        assert str(profile.parsed_cgpa) == "8.40"
        assert str(profile.recomputed_cgpa) == "8.41"

    @pytest.mark.parametrize("value", ["-1.0", "10.01", "99"])
    def test_an_impossible_cgpa_is_refused(self, as_student, value):
        response = as_student.post(
            reverse("my-confirm-cgpa"), {"cgpa": value}, format="json"
        )

        assert response.status_code == 400
