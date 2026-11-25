import { useEffect, useState } from 'react'
import { request } from './api'
import { useI18n } from './i18n'

export type Mode = 'demo' | 'live' | 'import'
export const offline = window.location.protocol === 'file:'
export const formatTime = (timestamp: string) => timestamp.replace('T', ' ').replace(/(?:\.\d+)?Z$/, ' UTC')
export const errorText = (error: unknown) => error instanceof Error ? error.message : String(error)
export const firstLine = (message: string) => message.split('\n')[0]

export function useData<T>(path: string, mode: Mode, sample: T) {
  const { language } = useI18n()
  const [result, setResult] = useState<{ path: string; data?: T; error?: string }>()
  useEffect(() => {
    if (mode !== 'live') return
    const controller = new AbortController()
    setResult(undefined)
    request<T>(path, { signal: controller.signal }, language).then(
      data => setResult({ path, data }),
      error => { if (!controller.signal.aborted) setResult({ path, error: errorText(error) }) },
    )
    return () => controller.abort()
  }, [path, mode, language])
  if (mode !== 'live') return { data: sample, pending: false, error: undefined }
  const current = result?.path === path ? result : undefined
  return { ...current, pending: !current }
}

/** Analysis results. They are read again when the backend has finished a new analysis; the old
 *  data stays visible meanwhile. An empty path loads nothing. */
export function useAnalysis<T>(path: string, keepPrevious = false) {
  const { language } = useI18n()
  const [revision, setRevision] = useState('')
  const [result, setResult] = useState<{ path: string; data?: T; error?: string }>()
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    request<T>(path, { signal: controller.signal }, language).then(
      data => setResult({ path, data }),
      error => { if (!controller.signal.aborted) setResult({ path, error: errorText(error) }) },
    )
    return () => controller.abort()
  }, [path, language, revision])
  useEffect(() => {
    if (!path) return
    const check = () => request<{ finished_at: string | null }>('/analysis/status').then(
      status => setRevision(status.finished_at ?? ''), () => undefined)
    const timer = setInterval(check, 10_000)
    return () => clearInterval(timer)
  }, [path])
  const current = path && result?.path === path ? result : undefined
  return { data: current?.data ?? (keepPrevious && path && !current ? result?.data : undefined), error: current?.error, pending: !!path && !current }
}

export function Feedback({ pending, error }: { pending: boolean; error?: string }) {
  const { t } = useI18n()
  return error ? <p className="notice error" role="alert">{error}</p> : pending ? <p className="notice" role="status">{t('loading.data')}</p> : null
}
