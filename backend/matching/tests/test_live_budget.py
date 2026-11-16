"""
G4: on the live analysis path a retry that cannot fit the budget is skipped.

One gemma4:e4b reply takes about 90 s on the demo Mac's CPU. Two cannot fit
under the 120 s request timeout, and a retry given only the leftover seconds
would time out and take the embedding's time with it.
"""

import pytest

from matching import llm
from matching.testing import FakeLLMClient, resume_reply
from profiles import analysis


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(analysis.time, "monotonic", clock)
    return clock


def slow_client(clock, replies, seconds=90):
    queue = list(replies)

    def reply(system, user):
        clock.now += seconds
        return queue.pop(0)

    return FakeLLMClient(reply)


def test_an_invalid_reply_falls_back_at_once_when_a_retry_cannot_fit(clock):
    inner = slow_client(clock, ["not json", resume_reply()])
    budgeted = analysis._BudgetedClient(inner, deadline=clock.now + 150)

    with pytest.raises(llm.LLMUnavailable, match="no time to retry"):
        llm.parse_resume_facts("Aarav Mehta", client=budgeted)

    assert len(inner.prompts) == 1
    assert clock.now == 1090  # 60 s still left for the embedding


def test_the_retry_still_runs_when_the_budget_has_room(clock):
    inner = slow_client(clock, ["not json", resume_reply()])
    budgeted = analysis._BudgetedClient(inner, deadline=clock.now + 1000)

    facts = llm.parse_resume_facts("Aarav Mehta aarav.mehta@college.edu", client=budgeted)

    assert len(inner.prompts) == 2
    assert facts.data["full_name"] == "Aarav Mehta"


def test_a_client_without_a_budget_always_retries():
    client = FakeLLMClient(["not json", resume_reply()])

    llm.parse_resume_facts("Aarav Mehta", client=client)

    assert len(client.prompts) == 2
