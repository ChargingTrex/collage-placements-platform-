/**
 * Horizontal bars for "how many in each category".
 *
 * Horizontal because the category names here are long ("Preparation for
 * competitive exams / UPSC") and vertical bars would turn them into angled
 * labels. One hue, not nine: length already encodes the magnitude, so colour
 * carrying it again would add nothing and spend the categorical palette on a
 * single series. That also means no legend -- the row label names each bar.
 *
 * Built from divs rather than a chart library: the whole mark is a width
 * percentage, and the project has no charting dependency to justify.
 */

export interface Bar {
  /** Stable key, and what `onSelect` reports. */
  key: string
  label: string
  value: number
}

export default function BarList({
  bars,
  total,
  selectedKey,
  onSelect,
  emptyLabel = 'Nothing to show yet.',
}: {
  bars: Bar[]
  /** Denominator for the share shown on hover. Defaults to the bar sum. */
  total?: number
  selectedKey?: string | null
  /** Makes the rows clickable. Clicking the selected row again clears it. */
  onSelect?: (key: string | null) => void
  emptyLabel?: string
}) {
  if (!bars.length) return <p className="py-6 text-center text-sm text-ink-400">{emptyLabel}</p>

  // Bars are scaled against the largest value, so the longest fills the track
  // and the rest stay comparable to it.
  const largest = Math.max(...bars.map((bar) => bar.value), 1)
  const denominator = total ?? bars.reduce((sum, bar) => sum + bar.value, 0)

  return (
    <ul className="space-y-1.5">
      {bars.map((bar) => {
        const share = denominator ? Math.round((bar.value / denominator) * 100) : 0
        const selected = selectedKey === bar.key
        // A non-zero count always shows a sliver: a bar that rounds to
        // nothing reads as "none", which is a different fact.
        const width = bar.value ? Math.max((bar.value / largest) * 100, 1.5) : 0
        const title = `${bar.label}: ${bar.value} student${bar.value === 1 ? '' : 's'}${
          denominator ? ` (${share}% of ${denominator})` : ''
        }`

        const row = (
          <>
            {/* Wraps rather than truncates: "Preparation for competitive
                exams / UPSC" is the label, and half of it is not a label. */}
            <span
              className={`text-sm leading-tight ${selected ? 'font-medium text-ink-900' : 'text-ink-800'}`}
            >
              {bar.label}
            </span>

            <span className="h-2.5 overflow-hidden rounded-sm bg-ink-100">
              <span
                className={`block h-full rounded-r-[4px] transition-[width,background-color] duration-300 ${
                  selected ? 'bg-brand-700' : 'bg-brand-500'
                }`}
                style={{ width: `${width}%` }}
              />
            </span>

            <span
              className={`text-right text-sm tabular-nums ${
                bar.value ? 'font-medium text-ink-900' : 'text-ink-400'
              }`}
            >
              {bar.value}
            </span>
          </>
        )

        // The grid is the same whether or not the row is interactive, so the
        // bars stay aligned across both charts on the page.
        const grid = 'grid grid-cols-[minmax(8rem,13rem)_1fr_2.5rem] items-center gap-3'

        return (
          <li key={bar.key}>
            {onSelect ? (
              <button
                type="button"
                title={title}
                aria-pressed={selected}
                onClick={() => onSelect(selected ? null : bar.key)}
                className={`${grid} w-full rounded-md px-2 py-1.5 text-left transition hover:bg-ink-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${
                  selected ? 'bg-brand-50' : ''
                }`}
              >
                {row}
              </button>
            ) : (
              <div className={`${grid} px-2 py-1.5`} title={title}>
                {row}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
