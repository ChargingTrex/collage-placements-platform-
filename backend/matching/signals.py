"""Keep the cached skill graph in step with the tables behind it."""

from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from matching.models import Skill, SkillAlias
from matching.skills import reset_skill_graph


def _invalidate(**kwargs):
    reset_skill_graph()
    # Again once the transaction commits: a read made inside it may have
    # cached rows that a rollback then undid.
    transaction.on_commit(reset_skill_graph)


for _model in (Skill, SkillAlias):
    post_save.connect(_invalidate, sender=_model, dispatch_uid=f"skill-graph-save-{_model.__name__}")
    post_delete.connect(_invalidate, sender=_model, dispatch_uid=f"skill-graph-delete-{_model.__name__}")


@receiver(m2m_changed, sender=Skill.implies.through, dispatch_uid="skill-graph-implies")
def _implies_changed(action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        _invalidate()
