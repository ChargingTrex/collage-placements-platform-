import {
  APPLICATION_STATUS_LABEL,
  OPPORTUNITY_STATUS_LABEL,
  type ApplicationStatus,
  type OpportunityStatus,
} from '@/api/opportunities'
import { Badge } from '@/components/ui'

const OPPORTUNITY_TONE = {
  draft: 'neutral',
  pending_review: 'warning',
  open: 'success',
  closed: 'neutral',
  rejected: 'danger',
} as const

const APPLICATION_TONE = {
  applied: 'brand',
  shortlisted: 'success',
  interview: 'success',
  offer: 'success',
  rejected: 'danger',
  withdrawn: 'neutral',
} as const

export function OpportunityStatusBadge({ status }: { status: OpportunityStatus }) {
  return <Badge tone={OPPORTUNITY_TONE[status]}>{OPPORTUNITY_STATUS_LABEL[status]}</Badge>
}

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return <Badge tone={APPLICATION_TONE[status]}>{APPLICATION_STATUS_LABEL[status]}</Badge>
}
