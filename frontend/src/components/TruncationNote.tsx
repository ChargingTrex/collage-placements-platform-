import { truncationOf, type Collected } from '@/api/paginate'
import { Alert } from '@/components/ui'

/** Shown whenever a list stopped before the last page. A cut is never silent. */
export default function TruncationNote({ collected }: { collected: Collected<unknown> | null }) {
  const cut = collected ? truncationOf(collected) : null
  if (!cut) return null
  return (
    <div className="mb-4">
      <Alert tone="warning">
        Showing the first {cut.shown} of {cut.total}. Narrow the list with the filters to see the
        rest.
      </Alert>
    </div>
  )
}
