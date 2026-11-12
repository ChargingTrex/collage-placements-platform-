import { describe, expect, it } from 'vitest'

import { describeError } from '@/api/client'

const UNKNOWN_FILTER =
  'Unknown filter. Use one of: department, batch, education_level, experience_months, skills, categories.'

describe('describeError', () => {
  it('uses a string detail as the message, with no field errors', () => {
    const error = describeError(429, { detail: 'Request was throttled. Expected available in 45 seconds.' })
    expect(error.status).toBe(429)
    expect(error.message).toBe('Request was throttled. Expected available in 45 seconds.')
    expect(error.fieldErrors).toEqual({})
  })

  it('keeps flat field lists as they are and leads with the first message', () => {
    const error = describeError(400, {
      prn: ['No roster entry matches this PRN.'],
      email: ['Enter a valid email address.', 'Use your college email.'],
    })
    expect(error.message).toBe('No roster entry matches this PRN.')
    expect(error.fieldErrors).toEqual({
      prn: ['No roster entry matches this PRN.'],
      email: ['Enter a valid email address.', 'Use your college email.'],
    })
  })

  it('wraps a plain string or other scalar field value in a list', () => {
    const error = describeError(403, { code: 'That code has expired.', needs_verification: true })
    expect(error.message).toBe('That code has expired.')
    expect(error.fieldErrors).toEqual({ code: ['That code has expired.'], needs_verification: ['true'] })
  })

  it('flattens a nested dict, as the match filters send it, into readable text', () => {
    const error = describeError(400, { filters: { age: UNKNOWN_FILTER } })
    expect(error.message).toBe(`age: ${UNKNOWN_FILTER}`)
    expect(error.fieldErrors).toEqual({ filters: [`age: ${UNKNOWN_FILTER}`] })
    expect(error.message).not.toContain('[object Object]')
  })

  it('flattens lists of dicts and numbered child errors, skipping the empty ones', () => {
    const error = describeError(400, {
      experience: [{}, { start_date: ['Enter a valid date.'], role: ['This field is required.'] }],
      student_ids: { 1: ['Must be a valid UUID.'] },
    })
    expect(error.fieldErrors).toEqual({
      experience: ['start_date: Enter a valid date.', 'role: This field is required.'],
      student_ids: ['Item 2: Must be a valid UUID.'],
    })
    expect(error.message).toBe('start_date: Enter a valid date.')
  })

  it('reads a top-level list of messages without inventing field names', () => {
    const error = describeError(400, ['Upload a resume first.'])
    expect(error.message).toBe('Upload a resume first.')
    expect(error.fieldErrors).toEqual({})
  })

  it('falls back to the status when the body says nothing usable', () => {
    expect(describeError(500, null).message).toBe('Request failed (500)')
    expect(describeError(502, {}).message).toBe('Request failed (502)')
    expect(describeError(400, { filters: {} }).message).toBe('Request failed (400)')
  })
})
