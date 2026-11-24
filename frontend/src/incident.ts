import type { Entry } from './demo'
import { translate } from './i18n'
import type { Language } from './i18n'

const isError = (entry: Entry) => /^(ERROR|FATAL)$/i.test(entry.level)
const isRetry = (entry: Entry) => /\bretr(?:y|ies|ied|ying)\b/i.test(entry.message)

export function incidentEvidence(selected: Entry, events: Entry[]) {
  const errors = events.filter(isError)
  const position = events.findIndex(entry => entry.id === selected.id)
  const nextError = events.slice(position + 1).find(isError)
  const previousError = events.slice(0, position).reverse().find(isError)
  const error = isError(selected) ? selected : nextError ?? previousError
  const errorPosition = error ? events.findIndex(entry => entry.id === error.id) : -1
  const before = error ? events.slice(0, errorPosition) : []
  const after = error ? events.slice(errorPosition + 1) : []
  const preceding = [...before].reverse().find(isError)
  const previousLog = before.at(-1)
  const following = after.find(entry => isError(entry) || isRetry(entry) || /\b(?:success|completed|recovered)\b/i.test(entry.message))
  return { errors, error, preceding, previousLog, following }
}



export function describeError(error: Entry, preceding?: Entry, language: Language = 'en') {
  const message = [preceding?.message, error.message].filter(Boolean).join(' ')
  if (/\b(?:missing assembly reference|reference.{0,55}(?:not found|not resolvable|missing|absent)|referenz.{0,55}(?:fehlt|nicht auflösbar))\b/i.test(message)) {
    return translate(language, 'error.missingReference')
  }
  if (/\bno space left on device\b|\bdisk (?:is )?full\b/i.test(message)) {
    return translate(language, 'error.diskSpace')
  }
  if (/\baccess denied\b|\bpermission denied\b|\bwrite permission\b|\bwrite access denied\b|\bzugriff verweigert\b/i.test(message)) {
    return translate(language, 'error.permission')
  }
  if (/\b(?:timed? out|timeout|zeitüberschreitung)\b/i.test(message)) {
    return translate(language, 'error.timeout')
  }
  return undefined
}
