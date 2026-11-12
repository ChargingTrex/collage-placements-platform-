import { useEffect, useRef, useState } from 'react'

import { ApiError } from '@/api/client'
import { rosterApi, type RosterStudent, type UploadResult } from '@/api/roster'
import { Alert, Badge, Button, Card, CardTitle, EmptyState, Field, PageHeader } from '@/components/ui'

export default function RosterPage() {
  const [students, setStudents] = useState<RosterStudent[]>([])
  const [count, setCount] = useState(0)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [dryRun, setDryRun] = useState(true)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  async function loadStudents(term = search) {
    setLoading(true)
    setListError(null)
    try {
      const page = await rosterApi.students({ search: term })
      setStudents(page.results)
      setCount(page.count)
    } catch (error) {
      setListError(error instanceof ApiError ? error.message : 'Could not load the roster.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadStudents('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleUpload() {
    if (!file) return
    setUploading(true)
    setUploadError(null)
    setResult(null)
    try {
      const uploaded = await rosterApi.upload(file, dryRun)
      setResult(uploaded)
      if (!uploaded.dry_run) {
        await loadStudents()
        setFile(null)
        if (fileInput.current) fileInput.current.value = ''
      }
    } catch (error) {
      setUploadError(
        error instanceof ApiError ? error.message : 'The file could not be processed.',
      )
    } finally {
      setUploading(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Student roster"
        subtitle="The master list every student account is checked against."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardTitle hint="CSV columns: prn, email, full_name, department, batch, cgpa, phone, is_placement_eligible.">
            Upload a roster
          </CardTitle>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="roster-file" className="block text-sm font-medium text-ink-800">
                CSV file
              </label>
              <input
                ref={fileInput}
                id="roster-file"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null)
                  setResult(null)
                  setUploadError(null)
                }}
                className="block w-full text-sm text-ink-600 file:mr-3 file:rounded-md file:border-0 file:bg-ink-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-ink-200"
              />
            </div>

            <label className="flex items-start gap-2 text-sm text-ink-600">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(event) => setDryRun(event.target.checked)}
                className="mt-0.5"
              />
              <span>
                Validate only — report what would change without saving anything.
              </span>
            </label>

            <Button onClick={handleUpload} loading={uploading} disabled={!file} className="w-full">
              {dryRun ? 'Check file' : 'Upload roster'}
            </Button>

            {uploadError ? <Alert tone="error">{uploadError}</Alert> : null}
            {result ? <UploadReport result={result} /> : null}
          </div>
        </Card>

        <Card className="lg:col-span-3">
          <CardTitle hint={`${count} student${count === 1 ? '' : 's'} on the roster.`}>
            Roster
          </CardTitle>

          <form
            className="mb-4 flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              void loadStudents()
            }}
          >
            <div className="flex-1">
              <Field
                label="Search"
                name="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="PRN, name, email or department"
              />
            </div>
            <Button type="submit" variant="secondary">
              Search
            </Button>
          </form>

          {listError ? <Alert tone="error">{listError}</Alert> : null}

          {loading ? (
            <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
          ) : students.length === 0 ? (
            <EmptyState title="No students yet">Upload a roster CSV to get started.</EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-ink-200 text-xs tracking-wide text-ink-400 uppercase">
                  <tr>
                    <th className="py-2 pr-4 font-medium">PRN</th>
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Department</th>
                    <th className="py-2 pr-4 font-medium">Batch</th>
                    <th className="py-2 pr-4 font-medium">CGPA</th>
                    <th className="py-2 font-medium">Account</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {students.map((student) => (
                    <tr key={student.id}>
                      <td className="py-2 pr-4 font-mono text-xs">{student.prn}</td>
                      <td className="py-2 pr-4">{student.full_name}</td>
                      <td className="py-2 pr-4 text-ink-600">{student.department}</td>
                      <td className="py-2 pr-4 text-ink-600">{student.batch}</td>
                      <td className="py-2 pr-4 text-ink-600">{student.cgpa ?? '—'}</td>
                      <td className="py-2">
                        {student.has_account ? (
                          <Badge tone="success">Registered</Badge>
                        ) : student.is_placement_eligible ? (
                          <Badge>Not yet</Badge>
                        ) : (
                          <Badge tone="danger">Ineligible</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

function UploadReport({ result }: { result: UploadResult }) {
  const tone = result.error_count > 0 ? 'warning' : 'success'
  const headline = result.dry_run
    ? `${result.processed} row(s) would apply`
    : `${result.created} created, ${result.updated} updated, ${result.unchanged} unchanged`

  return (
    <div className="space-y-3">
      <Alert tone={tone} title={headline}>
        {result.error_count > 0
          ? `${result.error_count} row(s) were rejected. ${
              result.dry_run
                ? 'Nothing was saved — fix them, or untick "validate only" to apply the rest.'
                : 'Everything else was applied.'
            }`
          : result.dry_run
            ? 'Nothing was saved. Untick "validate only" to apply it.'
            : 'The roster is up to date.'}
      </Alert>

      {result.errors.length > 0 ? (
        <div className="max-h-64 overflow-y-auto rounded-lg border border-ink-200">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-ink-50 text-ink-400 uppercase">
              <tr>
                <th className="px-3 py-2 font-medium">Row</th>
                <th className="px-3 py-2 font-medium">PRN</th>
                <th className="px-3 py-2 font-medium">Problem</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {result.errors.map((rowError) => (
                <tr key={`${rowError.row}-${rowError.prn}`}>
                  <td className="px-3 py-2 font-mono">{rowError.row}</td>
                  <td className="px-3 py-2 font-mono">{rowError.prn || '—'}</td>
                  <td className="px-3 py-2 text-ink-600">
                    {Object.entries(rowError.errors).map(([field, messages]) => (
                      <div key={field}>
                        <span className="font-medium text-ink-800">{field}</span>: {messages.join(' ')}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
