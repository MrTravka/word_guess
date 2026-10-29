// Real Chrome checks without a browser-driver dependency. Uses a temporary DB.
import { spawn } from 'node:child_process'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import net from 'node:net'
import assert from 'node:assert/strict'

const root = path.resolve(import.meta.dirname, '..')
const directory = path.join(root, '.cache', `accounts-browser-${Date.now()}`)
await mkdir(directory, { recursive: true })
const python = path.join(root, '.venv', 'Scripts', 'python.exe')
const profile = path.join(directory, 'chrome')
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const children = []
let socket
let send

async function freePort() {
  const server = net.createServer()
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise((resolve) => server.close(resolve))
  return port
}

function start(command, args, options = {}) {
  const child = spawn(command, args, { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...options })
  children.push(child)
  child.log = ''
  child.stdout?.on('data', (data) => { child.log += data })
  child.stderr?.on('data', (data) => { child.log += data })
  child.on('error', (error) => { child.log += error.message })
  return child
}

async function waitFor(predicate, description) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (await predicate()) return
    await pause(100)
  }
  throw new Error(`Timed out: ${description}`)
}

try {
  const env = { ...process.env, DATABASE_URL: `sqlite:///${path.join(directory, 'test.db').replaceAll('\\', '/')}`,
    COOKIE_SECURE: 'false', AUTH_ALLOWED_ORIGINS: '[]' }
  const bootstrap = start(python, ['-m', 'backend.app.bootstrap'], { env })
  assert.equal(await new Promise((resolve) => bootstrap.on('close', resolve)), 0, bootstrap.log)
  console.log('Temporary SQLite migrated and seeded')
  const port = await freePort()
  const server = start(python, ['-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', String(port)], { env })
  await waitFor(async () => {
    try { return (await fetch(`http://127.0.0.1:${port}/api/health`)).ok } catch { return false }
  }, 'API startup')
  console.log('API ready')
  let url = `http://127.0.0.1:${port}`
  if (process.argv.includes('--dev')) {
    const frontendPort = await freePort()
    start(process.execPath, [path.join(root, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'],
      { cwd: path.join(root, 'frontend'), env: { ...env, APP_PORT: String(port) } })
    const vite = children.at(-1)
    url = `http://127.0.0.1:${frontendPort}`
    await waitFor(async () => {
      if (vite.exitCode !== null) throw new Error(vite.log)
      try { return (await fetch(`${url}/api/health`)).ok } catch { return false }
    }, 'Vite proxy startup')
  }
  const chrome = start(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-background-networking', '--disable-extensions', '--remote-debugging-port=0',
    '--remote-debugging-address=127.0.0.1', `--user-data-dir=${profile}`, 'about:blank',
  ])
  let debugPort
  await waitFor(async () => {
    try { debugPort = (await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; return true }
    catch { if (chrome.exitCode !== null) throw new Error(chrome.log); return false }
  }, 'Chrome startup')
  console.log('Chrome ready')
  const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  socket = new WebSocket(pages.find((page) => page.type === 'page').webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
  const pending = new Map()
  let nextId = 0
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data)
    const entry = pending.get(message.id)
    if (!entry) return
    pending.delete(message.id)
    clearTimeout(entry.timer)
    if (message.error) entry.reject(new Error(JSON.stringify(message.error)))
    else entry.resolve(message.result)
  }
  send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)) }, 10000)
    pending.set(id, { resolve, reject, timer })
    socket.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async (expression) => {
    const response = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails))
    return response.result.value
  }
  const text = (value) => waitFor(() => evaluate(`document.body?.innerText.includes(${JSON.stringify(value)})`), value)
  const click = (value) => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent === ${JSON.stringify(value)}).click()`)
  const fill = (name, value) => evaluate(`(() => {
    const input = document.querySelector('input[name="${name}"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
  })()`)
  const background = () => evaluate('getComputedStyle(document.documentElement).backgroundColor')
  await send('Page.enable')
  await send('Network.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url })
  await text('Создать аккаунт')
  console.log('Guest page ready')
  await fill('display_name', 'Алиса')
  await fill('login', 'alice_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Алиса, рады видеть вас.')
  console.log('Registration passed')
  assert.equal(await evaluate('document.querySelectorAll("article").length'), 4)
  assert(await evaluate('Array.from(document.querySelectorAll("button")).find(b => b.textContent === "Играть").disabled'))
  assert.equal(await evaluate('document.cookie.includes("word_guess_session")'), false)
  assert.deepEqual(await evaluate('Object.keys(localStorage)'), ['word_guess_theme'])
  await click('Настройки')
  await text('Оформление')
  await evaluate('document.querySelector("input[value=dark]").click()')
  await text('Тема сохранена в аккаунте.')
  assert.equal(await background(), 'rgb(16, 23, 19)')
  // Observe the first computed background after navigation, before React starts.
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `
    document.addEventListener('DOMContentLoaded', () => {
      window.firstBackground = getComputedStyle(document.documentElement).backgroundColor;
    }, { once: true });
  ` })
  await send('Page.reload')
  await text('Алиса, рады видеть вас.')
  assert.equal(await evaluate('window.firstBackground'), 'rgb(16, 23, 19)')
  await click('Настройки')
  await text('Оформление')
  await evaluate('document.querySelector("input[value=light]").click()')
  await text('Тема сохранена в аккаунте.')
  await send('Emulation.setEmulatedMedia', { features: [
    { name: 'prefers-color-scheme', value: 'dark' }, { name: 'prefers-reduced-motion', value: 'reduce' },
  ] })
  assert.equal(await background(), 'rgb(245, 247, 246)')
  await evaluate('document.querySelector("input[value=system]").click()')
  await text('Тема сохранена в аккаунте.')
  assert.equal(await background(), 'rgb(16, 23, 19)')
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 900, deviceScaleFactor: 1, mobile: true })
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  await writeFile(path.join(directory, 'settings-phone.png'), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  await click('Выйти из аккаунта')
  await text('Создать аккаунт')
  console.log('Themes and logout passed')
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true)
  await writeFile(path.join(directory, 'account-phone.png'), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  await click('Вход')
  await fill('login', 'alice_browser')
  await fill('password', 'wrong-password')
  await click('Войти')
  await text('Неверный логин или пароль.')
  await fill('password', 'browser-password-123')
  await click('Войти')
  await text('Алиса, рады видеть вас.')
  // Revoke the cookie session externally, then simulate returning to the tab.
  await evaluate(`fetch('/api/auth/logout', { method: 'POST', headers: { 'X-Requested-With': 'word_guess' } })`)
  await evaluate(`window.dispatchEvent(new Event('focus'))`)
  await text('Создать аккаунт')
  await send('Network.setBlockedURLs', { urls: ['*api/auth/me*'] })
  await send('Page.reload')
  await text('Повторить вход')
  await send('Network.setBlockedURLs', { urls: [] })
  await click('Повторить вход')
  await text('Создать аккаунт')
  assert(server.exitCode === null, server.log)
  console.log(`PASS ${process.argv.includes('--dev') ? 'Vite proxy' : 'production'}: registration, login/error, HttpOnly, restore, themes before React, 360px, reduced motion, logout/revoke, network retry`)
  console.log(`Screenshots: ${directory}`)
} catch (error) {
  if (send && socket?.readyState === WebSocket.OPEN) {
    try {
      const result = await send('Runtime.evaluate', { expression: 'document.body.innerText', returnByValue: true })
      console.error(result.result.value)
    } catch { /* Preserve the original failure. */ }
  }
  throw error
} finally {
  if (send && socket?.readyState === WebSocket.OPEN) {
    try { await send('Browser.close') } catch { /* Process cleanup below. */ }
  }
  socket?.close()
  for (const child of children.reverse()) {
    if (child.exitCode === null) child.kill()
  }
}
