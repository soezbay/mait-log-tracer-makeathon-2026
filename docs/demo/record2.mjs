// Records the real Log Tracer UI in headless Edge over the DevTools protocol:
// screencast frames + the times and places of clicks, for the HyperFrames film.
import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'

const HERE = import.meta.dirname
const OUT = join(HERE, 'rec2')
rmSync(OUT, { recursive: true, force: true })
mkdirSync(join(OUT, 'frames'), { recursive: true })
const W = 1920, H = 1080, PORT = 9333
const sleep = ms => new Promise(r => setTimeout(r, ms))

const edge = spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(HERE, 'edgeprof')}`,
  `--window-size=${W},${H}`, '--hide-scrollbars', '--no-first-run', '--disable-extensions', 'about:blank'], { stdio: 'ignore' })

let target
for (let i = 0; i < 50 && !target; i++) {
  await sleep(200)
  try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page') } catch { }
}
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise(r => ws.addEventListener('open', r))
let id = 0
const pending = new Map(), frames = [], events = []
let t0 = null, location_dump
ws.addEventListener('message', async m => {
  const msg = JSON.parse(m.data)
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
  if (msg.method === 'Page.screencastFrame') {
    const { data, metadata, sessionId } = msg.params
    const n = frames.length
    writeFileSync(join(OUT, 'frames', `f${String(n).padStart(5, '0')}.jpg`), Buffer.from(data, 'base64'))
    frames.push(metadata.timestamp)
    send('Page.screencastFrameAck', { sessionId })
  }
})
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const i = ++id
    pending.set(i, msg => msg.error ? reject(new Error(method + ': ' + msg.error.message)) : resolve(msg.result))
    ws.send(JSON.stringify({ id: i, method, params }))
  })
}
const js = async expr => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result.value
const now = () => Date.now() / 1000 - t0
const mark = (name, extra = {}) => { events.push({ t: +now().toFixed(3), name, ...extra }); console.log(now().toFixed(1), name) }
async function waitFor(expr, ms = 20000) {
  const end = Date.now() + ms
  while (Date.now() < end) { if (await js(`!!(${expr})`)) return true; await sleep(150) }
  console.log('PAGE:', location_dump = await js(`location.href + ' | ' + document.body.innerText.slice(0, 400).replace(/\n/g, ' / ')`))
  throw new Error('timeout: ' + expr)
}
async function box(expr) {
  return js(`(() => { const e = ${expr}; if (!e) return null; e.scrollIntoView({block: 'nearest'}); const r = e.getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height} })()`)
}
async function click(name, expr) {
  const b = await box(expr)
  if (!b) throw new Error('not found: ' + name)
  mark('move', { name, x: b.x, y: b.y })
  await sleep(700) // the drawn cursor travels in this time
  mark('click', { name, x: b.x, y: b.y })
  for (const type of ['mousePressed', 'mouseReleased'])
    await send('Input.dispatchMouseEvent', { type, x: b.x, y: b.y, button: 'left', clickCount: 1 })
}
async function type(text, ms = 55) {
  mark('type', { text })
  for (const ch of text) { await send('Input.insertText', { text: ch }); await sleep(ms) }
}
async function scrollTo(name, expr, block = 'start') {
  mark('scroll', { name })
  await js(`(() => { const e = ${expr}; e && e.scrollIntoView({behavior: 'smooth', block: '${block}'}) })()`)
  await sleep(1400)
}
const byText = (sel, text) => `[...document.querySelectorAll(${JSON.stringify(sel)})].find(e => e.textContent.includes(${JSON.stringify(text)}))`

await send('Page.enable'); await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url: 'http://localhost:5173/' })
await sleep(1500)
await js(`localStorage.setItem('logtracer.language', 'de'); true`)
await send('Page.navigate', { url: 'http://localhost:5173/#/' })
await waitFor(`document.querySelectorAll('.metric').length > 3`, 40000)
await sleep(1500)

t0 = Date.now() / 1000
await send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: W, maxHeight: H, everyNthFrame: 1 })
mark('start'); await sleep(1500)

// timeline: filter a job, open one message
await click('nav timeline', byText('nav a', 'Zeitleiste'))
await waitFor(`location.hash.includes('timeline') && document.querySelectorAll('tbody tr').length > 5`)
await sleep(1500)
await click('job filter', `[...document.querySelectorAll('label')].find(l => l.textContent.trim().startsWith('Job-ID'))?.querySelector('input')`)
await type('JOB-2010', 80)
await waitFor(`[...document.querySelectorAll('tbody tr')].some(r => r.textContent.includes('JOB-2010'))`)
await sleep(2200)
mark('rows')
await click('message', `[...document.querySelectorAll('tbody tr')].find(r => r.textContent.includes('ERROR'))?.querySelector('button.link')`)
await waitFor(`document.querySelector('.event-view h2')`)
await sleep(3200)
mark('dialog')
await click('ask button', `document.querySelector('.event-questions button')`)
await waitFor(`location.hash.includes('chat') && document.querySelector('.run')`, 30000)
mark('running')
await waitFor(`document.querySelector('.run') && !document.querySelector('.run.running')`, 300000)
mark('answered', { state: await js(`document.querySelector('.run').className`), question: await js(`document.querySelector('.run .question')?.textContent`) })
await sleep(3000)
const h = await js(`document.scrollingElement.scrollHeight`)
mark('scroll answer', { height: h })
for (let y = 0; y < h; y += 260) { await js(`window.scrollTo({top: ${y}, behavior: 'smooth'})`); await sleep(650) }
await sleep(1500)

// data sources
await click('nav sources', byText('nav a', 'Datenquellen'))
await waitFor(`location.hash.includes('sources') && document.querySelectorAll('.metric').length > 5 && document.querySelectorAll('.source-table tbody tr').length > 10`)
await sleep(3000)
mark('sources')
await scrollTo('servers', `document.querySelector('.source-table')`, 'start')
await sleep(1800)
await scrollTo('files', `document.querySelector('.file-table')`, 'start')
await sleep(2200)
mark('end')
await send('Page.stopScreencast')
await sleep(500)
await send('Page.captureScreenshot', { format: 'png' }).then(r => writeFileSync(join(OUT, 'last.png'), Buffer.from(r.data, 'base64')))
writeFileSync(join(OUT, 'frames.json'), JSON.stringify({ t0: frames[0], times: frames }, null, 0))
writeFileSync(join(OUT, 'events.json'), JSON.stringify({ t0, events }, null, 1))
console.log('frames', frames.length)
ws.close(); edge.kill()
process.exit(0)
