import { useCallback, useEffect, useRef, useState } from 'react'
import { chat } from './api'
import { addStep, finishRun, RunPanel, startRun } from './assistant-run'
import type { AssistantRun } from './assistant-run'
import { errorText, Feedback, formatTime } from './data'
import type { Mode } from './data'
import { demoAnswer } from './demo'
import type { Answer } from './demo'
import { useI18n } from './i18n'
import { RichText } from './ui'

// The questions and answers of one chat. It lives above the pages, so it survives navigation and
// a question keeps running while the user looks at an incident or the timeline.

export type Turn = { id: number; question: string; run: AssistantRun | null; answer?: Answer; error?: string }

export function useConversation(mode: Mode) {
  const { language } = useI18n()
  const [turns, setTurns] = useState<Turn[]>([])
  const conversationId = useRef<string | undefined>(undefined)
  const active = useRef<{ id: number; controller: AbortController } | null>(null)
  const nextId = useRef(1)
  const change = useCallback((id: number, update: (turn: Turn) => Turn) =>
    setTurns(current => current.map(turn => turn.id === id ? update(turn) : turn)), [])

  const stop = useCallback(() => {
    const running = active.current
    if (!running) return
    active.current = null
    running.controller.abort()
    change(running.id, turn => ({ ...turn, run: turn.run && finishRun(turn.run, 'error') }))
  }, [change])

  const ask = useCallback(async (question: string) => {
    stop()
    const id = nextId.current++
    if (mode === 'demo') return setTurns([{ id, question, run: null, answer: demoAnswer(question, language) }])
    const controller = new AbortController()
    active.current = { id, controller }
    setTurns(current => [...current, { id, question, run: startRun(question) }])
    try {
      const { answer, usage } = await chat(question, step => {
        if (active.current?.id === id) change(id, turn => ({ ...turn, run: turn.run && addStep(turn.run, step) }))
      }, controller.signal, language, conversationId.current)
      if (active.current?.id !== id) return
      conversationId.current = usage?.conversation_id ?? conversationId.current
      change(id, turn => ({ ...turn, answer, run: turn.run && finishRun(turn.run, 'done', usage) }))
    } catch (error) {
      if (active.current?.id === id) change(id, turn => ({ ...turn, error: errorText(error), run: turn.run && finishRun(turn.run, 'error') }))
    } finally {
      if (active.current?.id === id) active.current = null
    }
  }, [mode, language, stop, change])

  const reset = useCallback(() => {
    active.current?.controller.abort()
    active.current = null
    conversationId.current = undefined
    setTurns([])
  }, [])
  const last = turns.at(-1)
  return { turns, ask, stop, reset, running: last?.run?.state === 'running' }
}
export type Conversation = ReturnType<typeof useConversation>

function Analysis({ answer, open }: { answer: Answer; open: (id: number) => void }) {
  const { t } = useI18n()
  return <>
    <h3>{t('assistant.hypothesis')}</h3><p>{answer.summary}</p>
    {answer.causal_chain.length > 0 && <><h3>{t('assistant.causalChain')}</h3><ol>{answer.causal_chain.map(item => <li key={item.step}><strong>{item.server}</strong> · {item.text}</li>)}</ol></>}
    {answer.evidence.length > 0 && <><h3>{t('assistant.evidence')}</h3><div className="evidence">{answer.evidence.map((item, index) => <button key={index} className="secondary" onClick={() => open(item.event_id)} title={item.file}>{item.file.split('/').at(-1)}:{item.line} <small>{formatTime(item.ts)}</small></button>)}</div></>}
    <h3>{t('assistant.uncertainty')}{typeof answer.confidence === 'number' ? ' · ' + t('assistant.confidence', { percent: Math.round(answer.confidence * 100) }) : ''}</h3><p>{answer.uncertainty}</p>
    {!!answer.counter_evidence?.length && <><h3>{t('assistant.counterEvidence')}</h3><ul>{answer.counter_evidence.map((text, index) => <li key={index}>{text}</li>)}</ul></>}
    {answer.verification_steps.length > 0 && <><h3>{t('assistant.verification')}</h3><ul>{answer.verification_steps.map((text, index) => <li key={index}>{text}</li>)}</ul></>}
  </>
}

/** One line for an older question: the question and the start of its answer. */
function firstSentence(text: string) {
  const sentence = text.split(/(?<=[.!?])\s/)[0] ?? ''
  return sentence.length > 140 ? sentence.slice(0, 137) + '…' : sentence
}

/** One question with its steps and answer. Older turns fold into one line; the newest is open. */
export function TurnView({ turn, latest, open }: { turn: Turn; latest: boolean; open: (id: number) => void }) {
  if (!latest) {
    const gist = turn.answer ? firstSentence(turn.answer.reply || turn.answer.summary) : turn.error ?? ''
    return <details className="turn turn-older">
      <summary><span className="turn-question">{turn.question}</span>{gist && <small>{gist}</small>}</summary>
      <TurnBody turn={turn} latest={false} open={open} />
    </details>
  }
  return <TurnBody turn={turn} latest open={open} />
}

function TurnBody({ turn, latest, open }: { turn: Turn; latest: boolean; open: (id: number) => void }) {
  const { t } = useI18n()
  const element = useRef<HTMLElement>(null)
  useEffect(() => { if (latest && turn.run?.state === 'running') element.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' }) }, [turn.id])
  const { answer } = turn
  const natural = answer?.reply && answer.reply !== answer.summary ? answer.reply : ''
  return <section className={latest ? 'turn' : 'turn-body'} ref={element}>
    {turn.run && <RunPanel run={turn.run} />}
    {answer && <article className="panel answer">
      {!turn.run && <p className="question">{turn.question}</p>}
      {natural && <RichText className="reply" text={natural} />}
      {natural
        ? <details key={String(latest)} className="analysis" open={latest}><summary>{t('assistant.analysis')}</summary><Analysis answer={answer} open={open} /></details>
        : <Analysis answer={answer} open={open} />}
    </article>}
    <Feedback pending={false} error={turn.error} />
  </section>
}
