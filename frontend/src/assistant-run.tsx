import { useEffect, useState } from 'react'
import type { ChatStep, ChatUsage } from './api'
import { useI18n } from './i18n'
import type { MessageKey } from './i18n'

// What the assistant did for a question: a timeline while it works, one line once it is done.

type StepState = 'running' | 'done' | 'warn' | 'error'
/** `tool` is null while the model itself works (planning, evaluating, writing the answer). */
type RunStep = { tool: string | null; label?: string; detail: string; result: string; state: StepState; phase?: 'plan' | 'evaluate' | 'answer'; start: number; end?: number }
export type AssistantRun = { question: string; state: 'running' | 'done' | 'error'; start: number; end?: number; steps: RunStep[]; usage?: ChatUsage }

const MIN_MODEL_MS = 300 // shorter gaps between two tool calls are not worth a line
const now = () => performance.now()

export function startRun(question: string): AssistantRun {
  const start = now()
  return { question, state: 'running', start, steps: [{ tool: null, phase: 'plan', detail: '', result: '', state: 'running', start }] }
}

/** End the open step of the model; drop it if it was only a short gap. */
function closeModel(steps: RunStep[], state: StepState, at: number) {
  const last = steps.at(-1)
  if (!last || last.tool !== null || last.state !== 'running') return steps
  if (state === 'done' && steps.length > 1 && at - last.start < MIN_MODEL_MS) return steps.slice(0, -1)
  return [...steps.slice(0, -1), { ...last, state, end: at }]
}

function describe(args: Record<string, unknown>) {
  const skip = new Set(['limit', 'n', 'window_seconds', 'offset'])
  return Object.entries(args)
    .filter(([key, value]) => !skip.has(key) && value !== null && value !== '' && typeof value !== 'object')
    .map(([key, value]) => key === 'event_id' ? '#' + value : String(value).replace(/T(\d\d:\d\d)(:\d\d)?Z$/, ' $1')).join(' · ')
}

export function addStep(run: AssistantRun, step: ChatStep): AssistantRun {
  const at = now()
  const known = step.tool ?? ''
  if (step.status === 'done') {
    const index = run.steps.map(item => item.tool === known && item.state === 'running').lastIndexOf(true)
    if (index < 0) return run
    const result = step.result ?? ''
    const steps = run.steps.map((item, i) => i === index ? { ...item, state: /^error/i.test(result) ? 'warn' as const : 'done' as const, result, end: at } : item)
    return { ...run, steps: [...steps, { tool: null, phase: 'evaluate', detail: '', result: '', state: 'running', start: at }] }
  }
  return { ...run, steps: [...closeModel(run.steps, 'done', at), { tool: known, label: step.message, detail: describe(step.args ?? {}), result: '', state: 'running', start: at }] }
}

export function finishRun(run: AssistantRun, state: 'done' | 'error', usage?: ChatUsage): AssistantRun {
  const at = now()
  const last = run.steps.at(-1)
  let steps = run.steps
  if (state === 'done' && last?.tool === null && last.state === 'running') steps = [...steps.slice(0, -1), { ...last, phase: 'answer', state: 'done', end: at }]
  else steps = steps.map(step => step.state === 'running' ? { ...step, state, end: at } : step)
  return { ...run, state, steps, usage, end: at }
}

const toolKeys: Record<string, MessageKey> = {
  get_stats: 'run.getStats', get_incidents: 'run.getIncidents', get_error_groups: 'run.getGroups', get_anomalies: 'run.getAnomalies',
  search_events: 'run.search', trace: 'run.trace', get_context: 'run.context', correlate: 'run.correlate',
}

export function RunPanel({ run }: { run: AssistantRun }) {
  const { language, t } = useI18n()
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const running = run.state === 'running'
  // Open while it works and after an error; folded once the answer is there. The user may change it.
  const [chosen, setChosen] = useState<boolean | null>(null)
  useEffect(() => setChosen(null), [run.start, run.state])
  const open = chosen ?? run.state !== 'done'
  const [, tick] = useState(0)
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => tick(value => value + 1), 500)
    return () => clearInterval(timer)
  }, [running])
  const time = (start: number, end?: number) => ((end ?? now()) - start < 10_000 && end !== undefined
    ? ((end - start) / 1000).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    : Math.round(((end ?? now()) - start) / 1000).toLocaleString(locale)) + ' s'
  const label = (step: RunStep) => {
    if (step.tool === null) return t(step.phase === 'plan' ? 'run.plan' : step.phase === 'answer' ? 'run.answer' : 'run.evaluate')
    const key = toolKeys[step.tool]
    return key ? t(key) : (step.label ?? step.tool).replace(/…$/, '')
  }
  const resultText = (step: RunStep) => {
    const rows = /^(\d+) of (\d+) rows$/.exec(step.result)
    if (rows) return t(rows[1] === rows[2] ? 'run.rows' : 'run.rowsOf', { count: Number(rows[1]).toLocaleString(locale), total: Number(rows[2]).toLocaleString(locale) })
    if (step.result === 'context loaded') return t('run.contextLoaded')
    return step.state === 'warn' ? t('run.failedStep') : step.result
  }
  const tools = run.steps.filter(step => step.tool !== null).length
  const current = run.steps.at(-1)
  const summary = running && current ? label(current)
    : t(run.state === 'error' ? 'run.stopped' : 'run.finished', { steps: t(tools === 1 ? 'run.stepOne' : 'run.stepMany', { count: tools }), time: time(run.start, run.end) })
  const usage = run.usage
  return <section className={'panel run ' + run.state}>
    <p className="question">{run.question}</p>
    <button type="button" className="run-toggle" aria-expanded={open} aria-controls="assistant-run" onClick={() => setChosen(!open)}>
      <span className={'run-icon ' + run.state} aria-hidden="true" /><span className="run-summary" role="status">{summary}</span>
      {running && <small aria-hidden="true">{time(run.start)}</small>}<span className="run-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
    </button>
    <div id="assistant-run" hidden={!open}>
      <ol className="run-steps">{run.steps.map((step, index) => <li key={index} className={step.state + (step.tool === null ? ' model' : '')}>
        <span className={'run-icon ' + step.state} aria-hidden="true" />
        <span className="run-text"><strong>{label(step)}</strong>{step.detail && <> <code>{step.detail}</code></>}{step.result && <small title={step.state === 'warn' ? step.result : undefined}>{resultText(step)}</small>}</span>
        <small className="run-time">{time(step.start, step.end)}</small>
      </li>)}</ol>
      {usage?.model && <p className="run-usage">{t('run.usage', { model: usage.model, calls: usage.llm_calls ?? 0, input: (usage.input_tokens ?? 0).toLocaleString(locale), output: (usage.output_tokens ?? 0).toLocaleString(locale) })}</p>}
    </div>
  </section>
}
