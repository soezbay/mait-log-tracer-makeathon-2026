const dateTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/

function toLocalDateTimeValue(date: Date) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function currentLocalDateTime() {
  return toLocalDateTimeValue(new Date())
}

export function browserTimeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time'
}

export function localDateTimeToEpoch(value: string) {
  return new Date(value).getTime()
}

export function localDateTimeToUtcIso(value: string) {
  return new Date(value).toISOString()
}

export function utcDateTimeToEpoch(value: string | null) {
  if (!value) return undefined
  if (dateTimePattern.test(value)) {
    const date = new Date(`${value}Z`)
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 16) === value ? date.getTime() : undefined
  }
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : undefined
}

export function utcDateTimeToLocal(value: string | null) {
  const timestamp = utcDateTimeToEpoch(value)
  return timestamp === undefined ? '' : toLocalDateTimeValue(new Date(timestamp))
}

export function isValidDateTimeLocal(value: string | null, max: string): value is string {
  if (!value || !dateTimePattern.test(value)) return false
  const date = new Date(value)
  return Number.isFinite(date.getTime()) && toLocalDateTimeValue(date) === value && value <= max
}
