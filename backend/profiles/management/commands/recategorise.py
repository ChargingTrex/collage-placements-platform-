"""
Re-sort analysed profiles into the current role categories.

    python manage.py recategorise                 # every analysed profile
    python manage.py recategorise --prn 220200921

Run after categories change (new JDs, an admin rename, merge or delete).
Cheap: each profile's stored vector is read back from the vector store, not
re-embedded, so the LLM server is not needed. The result is written to
`ResumeAnalysis.categories` and to the vector's filter metadata.
"""

from django.core.management.base import BaseCommand, CommandError

from matching import vectorstore
from matching.categories import categorise_profile
from profiles.analysis import vector_doc_id
from profiles.match import profile_skill_names
from profiles.models import ResumeAnalysis


class Command(BaseCommand):
    help = "Re-sort analysed student profiles into the current role categories."

    def add_arguments(self, parser):
        parser.add_argument("--prn", help="One student's profile.")

    def handle(self, *args, prn=None, **options):
        analyses = (
            ResumeAnalysis.objects.filter(status=ResumeAnalysis.Status.DONE)
            .select_related("profile__student")
            .prefetch_related("profile__skills")
            .order_by("profile__student__prn")
        )
        if prn:
            analyses = analyses.filter(profile__student__prn=prn)
            if not analyses.exists():
                raise CommandError(f"No analysed profile for PRN {prn}.")

        store = vectorstore.get_vector_store()
        changed = total = 0
        for analysis in analyses.iterator(chunk_size=200):
            profile = analysis.profile
            doc_id = vector_doc_id(profile)
            try:
                stored = store.get(doc_id)
            except Exception as exc:  # the store is optional; skills still sort
                self.stderr.write(f"{profile.prn}: vector store unavailable ({exc}); using skills only.")
                stored = None
            vector, model = (stored[0], stored[2]) if stored else (None, None)
            names = categorise_profile(vector, profile_skill_names(profile, analysis), model=model)

            total += 1
            if names != list(analysis.categories or []):
                analysis.categories = names
                analysis.save(update_fields=["categories", "updated_at"])
                changed += 1
            if stored:
                store.update_meta(doc_id, {"categories": names})
        self.stdout.write(self.style.SUCCESS(f"Recategorised {total}; {changed} changed."))
