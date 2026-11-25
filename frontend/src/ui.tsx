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
  return <span className={'badge ' + (status === 'failed' ? 'error' : status === 'recovered' ? 'info' : 'warn')}>{label}</span>
}
