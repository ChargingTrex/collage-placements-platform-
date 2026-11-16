"""D27: the company `shortlist` action and the `source` of a shortlist row."""

import pytest
from django.urls import reverse

from profiles.models import CompanyShortlist

pytestmark = pytest.mark.django_db


def make_application_row(company, profile):
    """What applying leaves behind, without going through the apply flow."""
    from django.core.files.base import ContentFile

    from opportunities.models import Application, Opportunity

    opp = Opportunity.objects.create(
        company=company, title="Role", description="Python work", role_type="full_time",
        deadline="2099-01-01", status="open",
    )
    application = Application(
        opportunity=opp, profile=profile, prn=profile.prn, full_name="Test Student",
        resume_snapshot_filename="r.pdf",
    )
    application.resume_snapshot.save("r.pdf", ContentFile(b"x"), save=False)
    application.save()
    CompanyShortlist.objects.get_or_create(
        company=company, profile=profile, defaults={"source": "application"}
    )
    return application


def test_a_new_manual_shortlist_row_has_source_manual(as_company, profile, company):
    response = as_company.post(reverse("company-profile-shortlist", args=[profile.student_id]), {"note": "n"})
    assert response.status_code == 201
    assert CompanyShortlist.objects.get(company=company, profile=profile).source == "manual"


def test_shortlisting_an_applicant_upgrades_their_row_to_manual(as_company, profile, company):
    make_application_row(company, profile)
    as_company.post(reverse("company-profile-shortlist", args=[profile.student_id]), {"note": "pick"})
    row = CompanyShortlist.objects.get(company=company, profile=profile)
    assert row.source == "manual" and row.note == "pick"


def test_unshortlisting_an_active_applicant_downgrades_the_row(as_company, profile, company):
    make_application_row(company, profile)
    as_company.post(reverse("company-profile-shortlist", args=[profile.student_id]), {})
    response = as_company.delete(reverse("company-profile-shortlist", args=[profile.student_id]))
    assert response.status_code == 204
    assert CompanyShortlist.objects.get(company=company, profile=profile).source == "application"


def test_unshortlisting_a_withdrawn_applicant_deletes_the_row(as_company, profile, company):
    application = make_application_row(company, profile)
    application.status = "withdrawn"
    application.save()
    as_company.post(reverse("company-profile-shortlist", args=[profile.student_id]), {})
    as_company.delete(reverse("company-profile-shortlist", args=[profile.student_id]))
    assert not CompanyShortlist.objects.filter(company=company, profile=profile).exists()


def test_unshortlisting_a_non_applicant_deletes_the_row(as_company, profile, company):
    as_company.post(reverse("company-profile-shortlist", args=[profile.student_id]), {})
    as_company.delete(reverse("company-profile-shortlist", args=[profile.student_id]))
    assert not CompanyShortlist.objects.filter(company=company, profile=profile).exists()


def test_an_application_to_another_company_does_not_keep_the_row(as_company, profile, company):
    from accounts.models import Company

    elsewhere = Company.objects.create(name="Elsewhere Ltd")
    make_application_row(elsewhere, profile)
    as_company.post(reverse("company-profile-shortlist", args=[profile.student_id]), {})
    as_company.delete(reverse("company-profile-shortlist", args=[profile.student_id]))
    assert not CompanyShortlist.objects.filter(company=company, profile=profile).exists()
