import type { ExperienceKind } from '@/api/profiles'

/** Shared by the experience form and the resume's experience suggestions. */
export const KINDS: Record<ExperienceKind, string> = {
  internship: 'Internship',
  part_time: 'Part-time',
  full_time: 'Full-time',
  volunteer: 'Volunteering',
  freelance: 'Freelance',
}
