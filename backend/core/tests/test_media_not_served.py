"""Student documents are reachable only through the audited API (DECISIONS D25)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_a_stored_resume_cannot_be_fetched_by_its_media_path(client, make_student, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    profile = make_student()
    profile.resume = SimpleUploadedFile("cv.pdf", b"%PDF-1.4 synthetic", content_type="application/pdf")
    profile.save()

    response = client.get(settings.MEDIA_URL + profile.resume.name)

    assert response.status_code == 404


def test_the_url_config_never_adds_a_media_route():
    # The test above runs with urls imported under test settings (DEBUG off),
    # so it alone cannot catch a DEBUG-only static() route coming back. This
    # one reads the source: re-adding `static(settings.MEDIA_URL, ...)` fails here.
    from pathlib import Path

    import config.urls

    source = Path(config.urls.__file__).read_text()
    assert "static(" not in source and "MEDIA_ROOT)" not in source
