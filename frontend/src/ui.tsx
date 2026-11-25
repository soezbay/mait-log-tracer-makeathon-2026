import type { PropsWithChildren, ReactNode } from 'react'
import { Tooltip } from '@mantine/core'
import { useI18n } from './i18n'

/** Small ⓘ that explains something on hover, focus or tap. */
export function InfoTip({ text }: { text: string }) {
  return <Tooltip label={text} multiline maw={320} position="bottom-start" withArrow events={{ hover: true, focus: true, touch: true }}>
    <button type="button" className="info-tip" aria-label={text}>i</button>
  </Tooltip>
}

/** One-line page title. The explanation sits behind the info icon, `children` at the right. */
export function PageTitle({ title, info, children }: PropsWithChildren<{ title: ReactNode; info?: string }>) {
  return <header className="page-title"><h1>{title}</h1>{info && <InfoTip text={info} />}{children && <div className="page-title-side">{children}</div>}</header>
}

export function LevelBadge({ level }: { level: string }) {
  return <span className={'badge ' + level.toLowerCase()}>{level}</span>
}

export function StatusBadge({ status }: { status: string | null }) {
  const { t } = useI18n()
  const label = status === 'failed' ? t('incidents.failed') : status === 'recovered' ? t('incidents.recovered') : t('incidents.unknown')
  return <span className={'badge ' + (status === 'failed' ? 'error' : status === 'recovered' ? 'ok' : 'warn')}>{label}</span>
}

/** **bold** and `code` inside a line of text. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, index) =>
    part.startsWith('**') && part.length > 4 ? <strong key={index}>{part.slice(2, -2)}</strong>
      : part.startsWith('`') && part.length > 2 ? <code key={index}>{part.slice(1, -1)}</code> : part)
}

/** Text of the assistant: paragraphs and simple lists, never HTML. */
export function RichText({ text, className }: { text: string; className?: string }) {
  const blocks: { kind: 'p' | 'ul' | 'ol'; lines: string[] }[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const item = /^(?:([-*•])|\d+[.)])\s+(.*)$/.exec(line)
    const kind = !item ? 'p' : item[1] ? 'ul' : 'ol'
    const last = blocks.at(-1)
    if (!line) blocks.push({ kind: 'p', lines: [] })
    else if (item && last?.kind === kind) last.lines.push(item[2])
    else blocks.push({ kind, lines: [item ? item[2] : line.replace(/^#+\s+/, '')] })
  }
  return <div className={className}>{blocks.filter(block => block.lines.length).map((block, index) => block.kind === 'p'
    ? <p key={index}>{inline(block.lines[0])}</p>
    : block.kind === 'ul' ? <ul key={index}>{block.lines.map((line, i) => <li key={i}>{inline(line)}</li>)}</ul>
      : <ol key={index}>{block.lines.map((line, i) => <li key={i}>{inline(line)}</li>)}</ol>)}</div>
}
