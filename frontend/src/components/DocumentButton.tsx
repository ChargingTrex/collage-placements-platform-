import { useState } from 'react'

import { downloadFile, openDocument } from '@/api/documents'
import { Button } from '@/components/ui'

/**
 * A button that opens an authenticated document and shows why it could not.
 * "Download" is separate from "Open" because saving from the browser's viewer
 * names the file after its blob: URL; this one keeps the uploaded filename.
 */
export default function DocumentButton({
  url,
  children,
  variant = 'secondary',
  filename = 'document',
}: {
  url: string
  children: string
  variant?: 'secondary' | 'ghost'
  /** Used only when the response carries no Content-Disposition name. */
  filename?: string
}) {
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function open() {
    setBusy(true)
    setError(null)
    try {
      await openDocument(url)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not open the document.')
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await downloadFile(url, filename)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not download the document.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <span className="inline-flex items-center gap-1.5">
        <Button size="sm" variant={variant} loading={busy} onClick={() => void open()}>
          {children}
        </Button>
        <Button size="sm" variant="ghost" loading={saving} onClick={() => void save()}>
          Download
        </Button>
      </span>
      {error ? (
        <span role="alert" className="text-xs text-bad-600">
          {error}
        </span>
      ) : null}
    </span>
  )
}
