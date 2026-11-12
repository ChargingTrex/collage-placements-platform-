/**
 * Sits under every page, signed in or out, so a tester always has somewhere
 * to report what they just hit. Rendered once at the app root rather than per
 * layout: the signed-out screens, the landing page and the 404 use different
 * wrappers and would each have had to remember it.
 */

/** The repo. Change these two and every page follows. */
const REPO_URL = 'https://github.com/ChargingTrex/collage-placements-platform-'
const ISSUES_URL = `${REPO_URL}/issues/new`

export default function SiteFooter() {
  return (
    <footer className="border-t border-ink-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-2 gap-y-1 px-6 py-5 text-sm text-ink-600">
        <span>Found a problem?</span>
        <a
          className="inline-flex items-center gap-1.5 font-medium text-brand-600 underline-offset-2 hover:underline"
          href={ISSUES_URL}
          target="_blank"
          rel="noreferrer noopener"
        >
          <GitHubMark />
          Raise an issue
        </a>
        <span className="text-ink-400">on GitHub</span>
      </div>
    </footer>
  )
}

/** Inline so the footer needs no icon dependency. */
function GitHubMark() {
  return (
    <svg
      viewBox="0 0 16 16"
      width="15"
      height="15"
      aria-hidden="true"
      fill="currentColor"
      className="shrink-0"
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-2.91-.88-2.91-3.08 0-.63.22-1.17.59-1.58-.04-.1-.26-.73.06-1.52 0 0 .62-.2 2.02.76.58-.16 1.2-.24 1.82-.24.62 0 1.24.08 1.82.24 1.4-.95 2.02-.76 2.02-.76.32.79.1 1.42.06 1.52.37.41.59.94.59 1.58 0 2.21-1.14 2.88-2.92 3.08.3.26.56.76.56 1.54 0 1.11-.01 2.02-.01 2.3 0 .21.15.46.55.38A7.99 7.99 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}
