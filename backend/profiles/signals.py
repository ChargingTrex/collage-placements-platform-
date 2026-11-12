"""
Keep the profile's vector honest.

The vector embeds the form as well as the resume, so a change to skills,
experience or projects leaves it describing a profile that no longer
exists: the analysis is marked for `manage.py reindex_vectors --dirty-only`.
A deleted profile, or a deleted analysis, takes its vector with it.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from profiles.models import ExperienceEntry, ProfileSkill, ProjectEntry, ResumeAnalysis, StudentProfile


def _form_changed(sender, instance, **kwargs):
    from profiles.analysis import mark_needs_reindex

    mark_needs_reindex(instance.profile_id)


for _model in (ProfileSkill, ExperienceEntry, ProjectEntry):
    post_save.connect(_form_changed, sender=_model, dispatch_uid=f"reindex-save-{_model.__name__}")
    post_delete.connect(_form_changed, sender=_model, dispatch_uid=f"reindex-delete-{_model.__name__}")


@receiver(post_delete, sender=StudentProfile, dispatch_uid="profile-vector-delete")
def _profile_deleted(sender, instance, **kwargs):
    from profiles.analysis import forget

    forget(instance)


@receiver(post_delete, sender=ResumeAnalysis, dispatch_uid="analysis-vector-delete")
def _analysis_deleted(sender, instance, **kwargs):
    """However the reading goes (Django admin, a queryset delete), its vector goes too."""
    from profiles.analysis import drop_vector

    try:
        profile = instance.profile
    except StudentProfile.DoesNotExist:
        return
    drop_vector(profile)
