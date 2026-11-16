import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import {
  describeApplyRefusal,
  formatSalary,
  opportunitiesApi,
  type FeedRow,
} from "@/api/opportunities";
import {
  MatchBreakdown,
  ScoreBar,
  SkillChips,
} from "@/components/MatchDisplay";
import { ApplicationStatusBadge } from "@/components/StatusBadges";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  PageHeader,
} from "@/components/ui";

function JobCard({
  row,
  onApplied,
}: {
  row: FeedRow;
  onApplied: (id: string, status: FeedRow["application_status"]) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  async function apply() {
    setBusy(true);
    setRefusal(null);
    try {
      const application = await opportunitiesApi.apply(row.id);
      onApplied(row.id, application.status);
    } catch (caught) {
      if (caught instanceof ApiError) {
        // Apply can be refused for several reasons (D28); each gets its own sentence.
        setRefusal(describeApplyRefusal(caught.reason, caught.message));
      } else setRefusal("Could not apply. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const matchLike = {
    score: row.score,
    components: row.components,
    matched_skills: row.matched_skills,
    missing_skills: row.missing_skills,
    hard_filter_failures: [],
    flagged: false,
    semantic_source: "",
  };

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{row.title}</h2>
          <p className="text-sm text-ink-600">
            {row.company_name ? `${row.company_name} · ` : ""}
            {row.role_type === "internship" ? "Internship" : "Full time"}
            {row.location ? ` · ${row.location}` : ""}
          </p>
          <p className="text-sm text-ink-600">
            {formatSalary(row)} · Deadline {row.deadline}
          </p>
        </div>
        {/* Eligibility is a flag beside the score, never part of it (D28). */}
        <Badge tone={row.eligible ? "success" : "warning"}>
          {row.eligible ? "Eligible" : "Not eligible"}
        </Badge>
      </div>

      <div className="max-w-xs">
        <ScoreBar score={row.score} size="sm" />
        <p className="mt-1 text-xs text-ink-400">
          A guide to where you stand, not a prediction.
        </p>
      </div>

      <SkillChips match={matchLike} />

      <details>
        <summary className="cursor-pointer text-sm text-brand-700">
          How this score is made up
        </summary>
        <div className="mt-2">
          <MatchBreakdown match={matchLike} />
        </div>
      </details>

      {!row.eligible && row.eligibility_reasons.length ? (
        <ul
          className="list-disc space-y-0.5 pl-5 text-sm text-warn-600"
          aria-label="Why you are not eligible"
        >
          {row.eligibility_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {refusal ? <Alert tone="error">{refusal}</Alert> : null}

      <div className="flex items-center gap-3">
        {row.has_applied && row.application_status ? (
          <>
            <span className="text-sm text-ink-600">Your application:</span>
            <ApplicationStatusBadge status={row.application_status} />
          </>
        ) : (
          <Button
            size="sm"
            loading={busy}
            disabled={!row.eligible}
            onClick={() => void apply()}
          >
            Apply
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function JobsPage() {
  const [rows, setRows] = useState<FeedRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    opportunitiesApi
      .feed()
      .then((next) => !cancelled && setRows(next))
      .catch((caught) => {
        if (!cancelled)
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Could not load the jobs.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const shown = useMemo(() => {
    if (!rows) return null;
    const needle = search.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) =>
      `${row.title} ${row.company_name ?? ""} ${row.required_skills.join(" ")}`
        .toLowerCase()
        .includes(needle),
    );
  }, [rows, search]);

  return (
    <>
      <PageHeader
        title="Jobs and internships"
        subtitle="Ranked by how well your profile and resume read against each posting."
      />
      <p className="mb-4 text-sm text-ink-600">
        Applying needs a resume on your profile.{" "}
        <Link to="/student/profile" className="font-medium underline">
          Open my profile
        </Link>
      </p>
      <div className="mb-4 max-w-sm">
        <Field
          label="Search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Title, company or skill"
        />
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {shown === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : shown && shown.length === 0 ? (
        <EmptyState title="Nothing to show">
          No open postings match right now.
        </EmptyState>
      ) : (
        <ul className="space-y-4" aria-label="Open postings">
          {shown?.map((row) => (
            <li key={row.id}>
              <JobCard
                row={row}
                onApplied={(id, status) =>
                  setRows((current) =>
                    current
                      ? current.map((r) =>
                          r.id === id
                            ? {
                                ...r,
                                has_applied: true,
                                application_status: status,
                              }
                            : r,
                        )
                      : current,
                  )
                }
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
