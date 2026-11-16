"""
Read a job description with the chat model ahead of time.

    python manage.py read_jd demo_jd.txt
    python manage.py read_jd - < demo_jd.txt
    python manage.py read_jd demo_jd.txt --timeout 300
    python manage.py read_jd demo_jd.txt --ttl 172800   # read the evening before

A live search gives an unread JD's chat reading only a few seconds
(`JD_READING_BUDGET_SECONDS`), far less than a CPU model needs. This command
has no budget: it waits for the reading, stores it under the exact cache key
the search uses, and feeds the role categories exactly as a recruiter's
search would (once per JD). Pasting the same text into the search afterwards
is then a cache hit: instant, with the model's reading and its category.

A leading UTF-8 BOM (Notepad) is dropped, then the text is trimmed the way
the search endpoint trims `jd_text`. The cache
must be shared with the server (`CACHE_BACKEND=file`); with the default
per-process memory cache the server never sees this reading. Profiles are
re-sorted into the categories afterwards (`recategorise`).

The reading is kept `--ttl` seconds (default `JD_CACHE_SECONDS`, a day),
counted from this run even when it was already cached, and the command
prints when it expires.
"""

import sys
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
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
            "--ttl",
            type=int,
            help="Seconds to keep the reading cached (default JD_CACHE_SECONDS, a day).",
        )
        parser.add_argument(
            "--no-recategorise", action="store_true", help="Do not re-sort profiles afterwards."
        )

    def handle(self, *args, path, timeout=None, ttl=None, no_recategorise=False, **options):
        ttl = settings.JD_CACHE_SECONDS if ttl is None else ttl
        if ttl <= 0:
            raise CommandError("--ttl must be a positive number of seconds.")
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
                with open(path, encoding="utf-8-sig") as handle:  # drops a Notepad BOM
                    raw = handle.read()
            except OSError as exc:
                raise CommandError(f"Cannot read {path}: {exc}") from exc
        # A BOM is not whitespace to strip(), and a browser never sends one.
        text = raw.lstrip("\ufeff").strip()  # then as the search serializer trims jd_text
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
        if vector is None:
            # Recording now would mark the JD as counted and leave its
            # category without a centroid for good. The reading is cached,
            # so a rerun costs only the embedding.
            raise CommandError("The JD was read but could not be embedded; nothing recorded. Run it again.")
        # From now, even for a reading that was already cached: a JD read
        # again on the demo's eve must last through the next day.
        cache.touch(llm.jd_cache_key(text, client.model), ttl)
        _record_once(text, facts, vector, embedder.model, reading_ttl=ttl)
        expires = datetime.now() + timedelta(seconds=ttl)

        self.stdout.write(
            self.style.SUCCESS(
                f"Read: {facts.canonical_role or '(no role)'}; required {', '.join(facts.required_skills) or '-'}; "
                f"embedded ({client.model}, {embedder.model})."
            )
        )
        self.stdout.write(
            f"The reading expires {expires:%a %d %b %H:%M} (in {ttl / 3600:g} h); "
            "paste the same text into the search before then."
        )
        if not no_recategorise:
            call_command("recategorise", stdout=self.stdout, stderr=self.stderr)
