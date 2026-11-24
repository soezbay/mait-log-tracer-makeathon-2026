export function currentUtcDateTimeLocal() {
  return new Date().toISOString().slice(0, 16)
}

export function isValidDateTimeLocal(value: string | null, max: string): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return false
  const date = new Date(`${value}Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 16) === value && value <= max
}
