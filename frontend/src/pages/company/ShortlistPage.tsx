import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import type { Collected } from '@/api/paginate'
import { ApiError } from '@/api/client'
import { downloadFile, saveBlob } from '@/api/documents'
import {
  profilesApi,
  SHORTLIST_RESUMES_URL,
  type CompanyProfile,
  type ShortlistContactsExport,
} from '@/api/profiles'
import TruncationNote from '@/components/TruncationNote'
import { Alert, Badge, Button, Card, CardTitle, EmptyState, PageHeader } from '@/components/ui'

function bytesFromBase64(encoded: string): Uint8Array<ArrayBuffer> {
  const binary = atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function contactsFailure(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (caught.status === 429) {
      return 'You are exporting too often. Wait a minute and try again.'
    }
    if (caught.status === 400) {
      return `Your shortlist is too large to export in one go. ${caught.message}`
    }
    return caught.message
  }
  return 'Could not export the contacts.'
}

/** What a finished contacts export leaves on screen. Lives in component state only. */
interface ContactsResult {
  password: string
  filename: string
  rowCount: number
}

function PasswordPanel({ result, onDone }: { result: ContactsResult; onDone: () => void }) {
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  async function copy() {
    try {
      await navigator.clipboard.writeText(result.password)
      setCopied('yes')
    } catch {
      setCopied('no')
    }
  }

  return (
    <section
      aria-label="Contacts export password"
      className="mt-4 space-y-3 rounded-xl border border-warn-600/40 bg-warn-50 p-4"
    >
      <p className="text-sm font-medium text-ink-900">
        Saved {result.filename} with {result.rowCount} student{result.rowCount === 1 ? '' : 's'}.
        Students who have not been verified are included with blank email and phone.
      </p>
      <p className="text-sm text-ink-800">
        Password for the zip. This will not be shown again: copy it now and keep it somewhere safe.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <code
          aria-label="Zip password"
          className="rounded-md bg-white px-3 py-1.5 font-mono text-sm break-all ring-1 ring-ink-200"
        >
          {result.password}
        </code>
        <Button size="sm" variant="secondary" onClick={() => void copy()}>
          Copy password
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          I have saved the password
        </Button>
      </div>
      {copied === 'yes' ? <p role="status" className="text-xs text-ink-600">Copied.</p> : null}
      {copied === 'no' ? (
        <p role="status" className="text-xs text-ink-600">
          Could not copy automatically. Select the password and copy it by hand.
        </p>
      ) : null}
    </section>
  )
}

export default function ShortlistPage() {
  const [rows, setRows] = useState<CompanyProfile[] | null>(null)
  const [count, setCount] = useState(0)
  const [cut, setCut] = useState<Collected<unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [zipBusy, setZipBusy] = useState(false)
  const [zipError, setZipError] = useState<string | null>(null)
  const [skipped, setSkipped] = useState<number | null>(null)

  const [contactsBusy, setContactsBusy] = useState(false)
  const [contactsError, setContactsError] = useState<string | null>(null)
  // The password is never persisted: not in storage, not in the URL.
  const [contacts, setContacts] = useState<ContactsResult | null>(null)

  const load = useCallback(async () => {
    try {
      const got = await profilesApi.shortlistedStudents()
      setRows(got.rows)
      // The server's own count, not how many rows were fetched.
      setCount(got.count)
      setCut(got)
      setError(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load your shortlist.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function removeFromShortlist(profile: CompanyProfile) {
    try {
      await profilesApi.unshortlist(profile.student_id)
      await load()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not update the shortlist.')
    }
  }

  async function downloadResumes() {
    setZipBusy(true)
    setZipError(null)
    setSkipped(null)
    try {
      const headers = await downloadFile(SHORTLIST_RESUMES_URL, 'shortlist-resumes.zip')
      const skippedCount = Number(headers?.get('X-Skipped-Without-Resume') ?? 0)
      setSkipped(Number.isFinite(skippedCount) ? skippedCount : 0)
    } catch (caught) {
      setZipError(
        caught instanceof ApiError && caught.status === 429
          ? 'You are downloading too often. Wait a minute and try again.'
          : caught instanceof Error
            ? caught.message
            : 'Could not download the resumes.',
      )
    } finally {
      setZipBusy(false)
    }
  }

  async function exportContacts() {
    setContactsBusy(true)
    setContactsError(null)
    setContacts(null)
    try {
      const result: ShortlistContactsExport = await profilesApi.exportShortlistContacts()
      saveBlob(
        new Blob([bytesFromBase64(result.zip_base64)], { type: 'application/zip' }),
        result.filename,
      )
      setContacts({
        password: result.password,
        filename: result.filename,
        rowCount: result.row_count,
      })
    } catch (caught) {
      setContactsError(contactsFailure(caught))
    } finally {
      setContactsBusy(false)
    }
  }

  const empty = rows !== null && rows.length === 0

  return (
    <>
      <PageHeader
        title="Shortlist"
        subtitle="Students you picked, and applicants you moved to shortlisted, interview or offer."
      />
      <TruncationNote collected={cut} />
      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      <Card className="mb-6">
        <CardTitle hint="Contact details come only from verified students. The zip is password protected.">
          Exports
        </CardTitle>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={rows === null || empty}
            loading={zipBusy}
            onClick={() => void downloadResumes()}
          >
            Download CVs (zip)
          </Button>
          <Button
            variant="secondary"
            disabled={rows === null || empty}
            loading={contactsBusy}
            onClick={() => void exportContacts()}
          >
            Export contacts
          </Button>
        </div>
        {zipError ? (
          <div className="mt-3">
            <Alert tone="error">{zipError}</Alert>
          </div>
        ) : null}
        {skipped !== null && skipped > 0 ? (
          <p role="status" className="mt-3 text-sm text-ink-800">
            {skipped} student{skipped === 1 ? '' : 's'} had no resume and {skipped === 1 ? 'was' : 'were'}{' '}
            skipped. The zip lists them in SKIPPED.txt.
          </p>
        ) : null}
        {contactsError ? (
          <div className="mt-3">
            <Alert tone="error">{contactsError}</Alert>
          </div>
        ) : null}
        {contacts ? <PasswordPanel result={contacts} onDone={() => setContacts(null)} /> : null}
      </Card>

      {rows === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : null}

      {empty ? (
        <EmptyState title="Your shortlist is empty">
          Shortlist students from{' '}
          <Link to="/company/students" className="font-medium underline">
            Browse students
          </Link>
          , or move an applicant to shortlisted. Exports need at least one student.
        </EmptyState>
      ) : null}

      {rows && rows.length > 0 ? (
        <>
          <p className="mb-3 text-sm text-ink-600">
            {count} student{count === 1 ? '' : 's'} on your shortlist
          </p>
          <ul className="space-y-4" aria-label="Shortlisted students">
            {rows.map((profile) => (
              <li key={profile.id}>
                <Card className="p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2">
                        <Link
                          to={`/company/students/${profile.student_id}`}
                          className="font-medium hover:underline"
                        >
                          {profile.student.full_name}
                        </Link>
                        {profile.is_verified ? <Badge tone="success">Verified</Badge> : null}
                      </p>
                      <p className="text-sm text-ink-600">
                        {profile.headline || '—'} · {profile.student.department} ·{' '}
                        {profile.student.batch}
                      </p>
                      <p className="mt-1 text-sm text-ink-400">
                        CGPA {profile.student.cgpa ?? '—'} · {profile.experience_years} yrs
                        experience
                        {profile.education_level ? ` · ${profile.education_level}` : ''}
                      </p>
                      {profile.skills.length ? (
                        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Skills">
                          {profile.skills.slice(0, 8).map((skill) => (
                            <li
                              key={skill.id}
                              className="rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-600"
                            >
                              {skill.name}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void removeFromShortlist(profile)}
                    >
                      Remove from shortlist
                    </Button>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  )
}
