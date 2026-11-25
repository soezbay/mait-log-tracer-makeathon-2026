// Analyse an uploaded ZIP with the backend ("Analyze on server") and switch back to the original
// log package. The backend extracts the ZIP, runs the normal ingest + analysis and makes it the
// active data set, so Live mode, the incidents and the assistant all work on it.
import { request } from './api'
import type { Language } from './i18n'

export type Dataset = { kind: 'original' | 'upload'; name: string; activated_at: string | null; files: number | null }
export type DatasetState = { dataset: Dataset; running: boolean; error: string | null; last_result: Record<string, unknown> | null }

export const getDataset = (language: Language, signal?: AbortSignal) =>
  request<DatasetState>('/ingest/dataset', { signal }, language)

export function uploadDataset(file: File, language: Language) {
  return request<DatasetState>('/ingest/upload?name=' + encodeURIComponent(file.name), {
    method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file,
  }, language)
}

export const restoreOriginal = (language: Language) =>
  request<DatasetState>('/ingest/original', { method: 'POST' }, language)

/** Poll until the backend has finished the ingest and the analysis of the data set. */
export async function waitForDataset(language: Language, signal?: AbortSignal): Promise<DatasetState> {
  for (;;) {
    const state = await getDataset(language, signal)
    if (!state.running) {
      if (state.error) throw new Error(state.error)
      return state
    }
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
}
