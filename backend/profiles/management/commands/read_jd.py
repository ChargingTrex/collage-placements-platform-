"""
Read a job description with the chat model ahead of time.

    python manage.py read_jd demo_jd.txt
    python manage.py read_jd - < demo_jd.txt
    python manage.py read_jd demo_jd.txt --timeout 300

A live search gives an unread JD's chat reading only a few seconds
(`JD_READING_BUDGET_SECONDS`), far less than a CPU model needs. This command
has no budget: it waits for the reading, stores it under the exact cache key
the search uses, and feeds the role categories exactly as a recruiter's
search would (once per JD). Pasting the same text into the search afterwards
is then a cache hit: instant, with the model's reading and its category.

The text is trimmed the way the search endpoint trims `jd_text`. The cache
must be shared with the server (`CACHE_BACKEND=file`); with the default
per-process memory cache the server never sees this reading. Profiles are
re-sorted into the categories afterwards (`recategorise`).
"""

import sys

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from matching import llm
from matching.embeddings import get_embedder
from matching.serializers import JD_MAX_CHARS, JD_MIN_CHARS
from profiles.match import _record_once


class Command(BaseCommand):
    help = "Read a JD with the chat model ahead of a demo, into the search's cache and categories."
    stealth_options = ("stdin",)

    def add_arguments(self, parser):
        parser.add_argument("path", help="A text file with the JD, or - for stdin.")
        parser.add_argument(
            "--timeout", type=float, help="Seconds per model request (default LLM_TIMEOUT_SECONDS)."
        )
        parser.add_argument(
            "--no-recategorise", action="store_true", help="Do not re-sort profiles afterwards."
        )

    def handle(self, *args, path, timeout=None, no_recategorise=False, **options):
        if not llm.llm_enabled():
            raise CommandError("The LLM is disabled (LLM_ENABLED); nothing can read the JD.")
        if settings.CACHES["default"]["BACKEND"].endswith("LocMemCache"):
            self.stderr.write(
                "Warning: the cache is per-process memory, so the server will not see this reading. "
                "Set CACHE_BACKEND=file for both this command and the server."
            )

        if path == "-":
            raw = (options.get("stdin") or sys.stdin).read()
        else:
            try:
                with open(path, encoding="utf-8") as handle:
                    raw = handle.read()
            except OSError as exc:
                raise CommandError(f"Cannot read {path}: {exc}") from exc
        text = raw.strip()  # as the search serializer trims jd_text
        if not JD_MIN_CHARS <= len(text) <= JD_MAX_CHARS:
            raise CommandError(f"A JD must be {JD_MIN_CHARS} to {JD_MAX_CHARS} characters; this is {len(text)}.")

        client = llm.get_client()
        if timeout is not None:
            client.timeout = timeout
        try:
            facts = llm.parse_job_description(text, client=client)
        except llm.LLMUnavailable as exc:
            raise CommandError(f"The model could not read the JD: {exc}") from exc

        embedder = get_embedder(client)
        vector = embedder.try_embed(text)
        _record_once(text, facts, vector, embedder.model if vector is not None else None)

        self.stdout.write(
            self.style.SUCCESS(
                f"Read: {facts.canonical_role or '(no role)'}; required {', '.join(facts.required_skills) or '-'}; "
                f"{'embedded' if vector is not None else 'NOT embedded'} ({client.model})."
            )
        )
        if not no_recategorise:
            call_command("recategorise", stdout=self.stdout, stderr=self.stderr)
