import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { request } from './api'
import { useI18n } from './i18n'

// Questions offered in the Live assistant. They come from four places:
// - the logs (GET /api/suggestions)
// - the event or job the user opened last (GET /api/suggestions?event_id=…)
// - questions asked before and questions saved as favorites (this browser only)

export type Suggestion = { kind: string; question: string; reason: string; job_id: string | null; event_id: number | null; last_ts: string | null }
type Suggestions = { scope: 'logs' | 'event'; event_id: number | null; items: Suggestion[] }

/** Lets any view hand a question to the assistant. `live` is false in the Demo and ZIP modes. */
export type AssistantLink = { live: boolean; ask: (question: string) => void; setContext: (eventId: number) => void }
export const AssistantLinkContext = createContext<AssistantLink>({ live: false, ask: () => undefined, setContext: () => undefined })

const MAX_RECENT = 8
const MAX_FAVORITES = 20
const sameQuestion = (first: string, second: string) => first.trim().toLowerCase() === second.trim().toLowerCase()

function readList(key: string): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && !!item.trim()) : []
  } catch {
    return []
  }
}

function useStoredQuestions(key: string, max: number) {
  const [questions, setQuestions] = useState(() => readList(key).slice(0, max))
  const update = useCallback((change: (current: string[]) => string[]) => {
    setQuestions(current => {
      const next = change(current).slice(0, max)
      try { localStorage.setItem(key, JSON.stringify(next)) } catch { /* Storage may be disabled; keep the list for this visit. */ }
      return next
    })
  }, [key, max])
  const remove = useCallback((question: string) => update(current => current.filter(item => !sameQuestion(item, question))), [update])
  const add = useCallback((question: string) => {
    const text = question.trim()
    if (text) update(current => [text, ...current.filter(item => !sameQuestion(item, text))])
  }, [update])
  const clear = useCallback(() => update(() => []), [update])
  const has = (question: string) => questions.some(item => sameQuestion(item, question))
  return { questions, add, remove, clear, has }
}

export function useSavedQuestions() {
  const recent = useStoredQuestions('logtracer.assistant.recent', MAX_RECENT)
  const favorites = useStoredQuestions('logtracer.assistant.favorites', MAX_FAVORITES)
  return { recent, favorites }
}
export type SavedQuestions = ReturnType<typeof useSavedQuestions>

function useSuggestions(eventId: number | null | undefined) {
  const { language } = useI18n()
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<{ path: string; items?: Suggestion[]; error?: string }>()
  const [pending, setPending] = useState(false)
  const path = eventId === undefined || eventId === null
    ? '/suggestions?lang=' + language
    : '/suggestions?event_id=' + eventId + '&lang=' + language
  const active = eventId !== null
  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    setPending(true)
    request<Suggestions>(path, { signal: controller.signal }, language).then(
      data => setState({ path, items: data.items }),
      error => { if (!controller.signal.aborted) setState({ path, error: error instanceof Error ? error.message : String(error) }) },
    ).finally(() => { if (!controller.signal.aborted) setPending(false) })
    return () => controller.abort()
  }, [path, active, language, revision])
  const current = active && state?.path === path ? state : undefined
  return { items: current?.items, error: current?.error, pending, reload: () => setRevision(value => value + 1) }
}

function FavoriteButton({ question, saved }: { question: string; saved: SavedQuestions }) {
  const { t } = useI18n()
  const active = saved.favorites.has(question)
  const label = t(active ? 'suggest.removeFavorite' : 'suggest.addFavorite')
  return <button type="button" className="icon-button" aria-pressed={active} aria-label={label + ': ' + question} title={label}
    onClick={() => active ? saved.favorites.remove(question) : saved.favorites.add(question)}>{active ? '★' : '☆'}</button>
}

type ListProps = { items: { question: string; reason?: string }[]; saved: SavedQuestions; isOpen: (question: string) => boolean; ask: (question: string) => void; remove?: (question: string) => void }

function QuestionList({ items, saved, isOpen, ask, remove }: ListProps) {
  const { t } = useI18n()
  return <ul className="suggestion-list">{items.map(item => <li key={item.question}>
    <button type="button" className="secondary" disabled={isOpen(item.question)} onClick={() => ask(item.question)}>{item.question}{item.reason && <small>{item.reason}</small>}</button>
    <FavoriteButton question={item.question} saved={saved} />
    {remove && <button type="button" className="icon-button" aria-label={t('suggest.remove') + ': ' + item.question} title={t('suggest.remove')} onClick={() => remove(item.question)}>×</button>}
  </li>)}</ul>
}

/** All suggestions of the Live assistant. Folded while an answer is shown, so the answer stays on top. */
export function SuggestionPanel({ contextId, clearContext, saved, isOpen, ask, expanded, setExpanded }: {
  contextId: number | null; clearContext: () => void; saved: SavedQuestions; isOpen: (question: string) => boolean
  ask: (question: string) => void; expanded: boolean; setExpanded: (value: boolean) => void
}) {
  const { t } = useI18n()
  const context = useSuggestions(contextId)
  const logs = useSuggestions(undefined)
  const list = { saved, isOpen, ask }
  return <section className="panel suggestions">
    <div className="section-title"><h2>{t('suggest.title')}</h2>
      <button type="button" className="secondary" aria-expanded={expanded} aria-controls="suggestion-groups" onClick={() => setExpanded(!expanded)}>{t(expanded ? 'suggest.hide' : 'suggest.show')}</button></div>
    <div id="suggestion-groups" hidden={!expanded}>
      {contextId !== null && !!context.items?.length && <section>
        <div className="section-title"><h3>{t('suggest.context', { id: contextId })}</h3><button type="button" className="icon-button" aria-label={t('suggest.clearContext')} title={t('suggest.clearContext')} onClick={clearContext}>×</button></div>
        <QuestionList items={context.items} {...list} />
      </section>}
      <section>
        <div className="section-title"><h3>{t('suggest.logs')}</h3><button type="button" className="icon-button" disabled={logs.pending} aria-label={t('suggest.refresh')} title={t('suggest.refresh')} onClick={logs.reload}>↻</button></div>
        {logs.error ? <p className="notice error" role="alert">{t('suggest.unavailable')} {logs.error}</p>
          : !logs.items ? <p role="status">{t('loading.data')}</p>
            : logs.items.length ? <QuestionList items={logs.items} {...list} /> : <p>{t('suggest.noErrors')}</p>}
      </section>
      <div className="suggestion-columns">
        <section>
          <h3>{t('suggest.favorites')}</h3>
          {saved.favorites.questions.length
            ? <QuestionList items={saved.favorites.questions.map(question => ({ question }))} {...list} />
            : <p>{t('suggest.noFavorites')}</p>}
        </section>
        <section>
          <div className="section-title"><h3>{t('suggest.recent')}</h3>{saved.recent.questions.length > 0 && <button type="button" className="link" onClick={saved.recent.clear}>{t('suggest.clearRecent')}</button>}</div>
          {saved.recent.questions.length
            ? <QuestionList items={saved.recent.questions.map(question => ({ question }))} remove={saved.recent.remove} {...list} />
            : <p>{t('suggest.noRecent')}</p>}
        </section>
      </div>
    </div>
  </section>
}

/** Questions about one event, shown next to the event or job itself. Nothing outside Live. */
export function EventQuestions({ id }: { id: number }) {
  const { t } = useI18n()
  const { live, ask } = useContext(AssistantLinkContext)
  const { items } = useSuggestions(live ? id : null)
  if (!live || !items?.length) return null
  return <section className="event-questions"><h3>{t('suggest.askAbout')}</h3>
    <div className="actions">{items.map(item => <button type="button" className="secondary" key={item.question} onClick={() => ask(item.question)}>{item.question}</button>)}</div>
  </section>
}
