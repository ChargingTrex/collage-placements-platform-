"""`?prns=` responses name the PRNs the lookup could not find."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestUnmatchedPrns:
    def test_roster_list_names_the_misses_in_normalised_form(self, as_admin, roster_student):
        response = as_admin.get(
            reverse("roster-student-list"),
            {"prns": f"{roster_student.prn}, 999999999 ,abc123"},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["results"]) == 1
        assert body["unmatched_prns"] == ["999999999", "ABC123"]

    def test_no_prns_param_means_no_key(self, as_admin, roster_student):
        body = as_admin.get(reverse("roster-student-list")).json()
        assert "unmatched_prns" not in body

    def test_misses_are_computed_over_the_whole_set_not_one_page(self, as_admin):
        from roster.models import Student

        prns = [f"2202009{n:02d}" for n in range(21)]
        for n, prn in enumerate(prns):
            Student.objects.create(
                prn=prn, email=f"s{n}@college.edu", full_name=f"S{n}",
                department="CE", batch=2026, cgpa="7.0",
            )
        # 21 matches over 20-row pages: the last PRN sits on page 2, so a
        # per-page check on page 1 would wrongly call it missing.
        response = as_admin.get(
            reverse("roster-student-list"), {"prns": ",".join(prns) + ",999999999"}
        )
        body = response.json()
        assert len(body["results"]) == 20
        assert body["unmatched_prns"] == ["999999999"]
