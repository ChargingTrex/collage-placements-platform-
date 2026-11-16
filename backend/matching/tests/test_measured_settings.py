"""
The four numbers measured on nomic-embed-text (SMOKE_TESTS.md, V5): each can
be set from the environment, and `.env.example` documents the same defaults
the settings use, so a copied `.env` cannot quietly undo the measurement.

Settings are read once at import, so each case reads them in a subprocess.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = BACKEND.parent / ".env.example"

#: env var -> path into settings
MEASURED = {
    "MATCH_EMBEDDING_FLOOR": ("MATCH_SCORE", "CALIBRATION", "embedding", "FLOOR"),
    "MATCH_EMBEDDING_CEILING": ("MATCH_SCORE", "CALIBRATION", "embedding", "CEILING"),
    "CATEGORY_MERGE_THRESHOLD": ("CATEGORY", "MERGE_THRESHOLD"),
    "CATEGORY_MIN_FIT": ("CATEGORY", "MIN_FIT"),
    "SKILL_ALIAS_SUGGESTION_THRESHOLD": ("SKILL_GRAPH", "ALIAS_SUGGESTION_THRESHOLD"),
}

_READ = """
import json, os, sys
sys.path.insert(0, os.getcwd())
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.conf import settings
paths = json.loads(sys.argv[1])
out = {}
for name, path in paths.items():
    value = getattr(settings, path[0])
    for key in path[1:]:
        value = value[key]
    out[name] = value
print(json.dumps(out))
"""


def read_settings(**env) -> dict:
    clean = {k: v for k, v in os.environ.items() if k not in MEASURED}
    # A developer .env that sets one of these overrides the default checks.
    clean.update(env)
    result = subprocess.run(
        [sys.executable, "-c", _READ, json.dumps(MEASURED)],
        cwd=BACKEND, env=clean, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def env_example_values() -> dict:
    values = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() in MEASURED:
            values[name.strip()] = float(value)
    return values


def test_each_measured_number_can_be_set_from_the_environment():
    wanted = {name: 0.123 + i / 100 for i, name in enumerate(MEASURED)}
    assert read_settings(**{k: str(v) for k, v in wanted.items()}) == wanted


def test_env_example_lists_each_measured_number_with_the_settings_default():
    documented = env_example_values()
    assert set(documented) == set(MEASURED)
    assert documented == read_settings()


def test_the_defaults_are_the_nomic_measurements():
    assert read_settings() == {
        "MATCH_EMBEDDING_FLOOR": 0.50,
        "MATCH_EMBEDDING_CEILING": 0.88,
        "CATEGORY_MERGE_THRESHOLD": 0.75,
        "CATEGORY_MIN_FIT": 0.45,
        "SKILL_ALIAS_SUGGESTION_THRESHOLD": 0.78,
    }
