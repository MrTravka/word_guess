// Real Chrome checks without a browser-driver dependency. Uses a temporary DB.
import { spawn } from 'node:child_process'
import { cp, readFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import net from 'node:net'
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { randomUUID } from 'node:crypto'
import { createProtocol } from './chrome_protocol.mjs'

const root = path.resolve(import.meta.dirname, '..')
// Keep Chromium's nested CacheStorage paths below Windows legacy path limits.
const directory = path.join(root, '.cache', `accounts-browser-${Date.now()}-${randomUUID().slice(0, 8)}`)
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
  const pwaTest = process.argv.includes('--pwa')
  const testFrontend = path.join(directory, 'dist')
  if (pwaTest) await cp(path.join(root, 'frontend/dist'), testFrontend, { recursive: true })
  const env = { ...process.env, DATABASE_URL: `sqlite:///${path.join(directory, 'test.db').replaceAll('\\', '/')}`,
    COOKIE_SECURE: 'false', AUTH_ALLOWED_ORIGINS: '[]', ...(pwaTest ? { TEST_FRONTEND_DIST: testFrontend } : {}) }
  const bootstrap = start(python, ['-m', 'backend.app.bootstrap'], { env })
  assert.equal(await new Promise((resolve) => bootstrap.on('close', resolve)), 0, bootstrap.log)
  console.log('Temporary SQLite migrated and seeded')
  const port = await freePort()
  const application = pwaTest ? ['pwa_server:create_test_app', '--factory', '--app-dir', path.join(root, 'tests')] : ['backend.app.main:app']
  const server = start(python, ['-m', 'uvicorn', ...application, '--host', '127.0.0.1', '--port', String(port)], { env })
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
  send = createProtocol(socket, waitFor)
  const evaluate = async (expression, userGesture = false) => {
    const response = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture })
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails))
    return response.result.value
  }
  const text = (value) => waitFor(() => evaluate(`document.body?.innerText.includes(${JSON.stringify(value)})`), value)
  const click = (value) => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent === ${JSON.stringify(value)}).click()`, true)
  const fill = (name, value) => evaluate(`(() => {
    const input = document.querySelector('input[name="${name}"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
  })()`)
  const background = () => evaluate('getComputedStyle(document.documentElement).backgroundColor')
  const setAnswer = async (gameId, word) => {
    // Test fixtures only: this database lives in the unique .cache test folder.
    const source = `import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
w=c.execute('SELECT id,display_word FROM words WHERE canonical_word=?',(sys.argv[3],)).fetchone()
assert w
r=c.execute("UPDATE games SET word_id=?,answer=?,display_answer=? WHERE id=? AND status='active' AND version=0",(w[0],sys.argv[3],w[1],sys.argv[2]))
assert r.rowcount==1
c.commit()
c.close()`
    await promisify(execFile)(python, ['-c', source, path.join(directory, 'test.db'), gameId, word], { windowsHide: true })
  }
  const prepareChests = async () => {
    // Exercise the real campaign services, then seed six controlled cosmetic outcomes.
    const source = `import json,sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import select
from backend.app.config import Settings
from backend.app.database import create_database
from backend.app.models import User
from backend.app.campaign_models import Chest
from backend.app.chest_service import open_chest
from backend.app.game_service import create_game, mutate_game, owned_game
engine=create_database(Settings(_env_file=None,database_url='sqlite:///'+sys.argv[1].replace('\\\\','/')))
with engine.connect() as c:
    user=c.execute(select(User.id).where(User.login=='chests_browser')).scalar_one()
for level in range(1,101):
    with engine.connect().execution_options(sqlite_immediate=True) as c,c.begin():
        g=create_game(c,user,'campaign',str(uuid4()))
        word=owned_game(c,g['id'],user)['answer']
        mutate_game(c,user,g['id'],'guess',SimpleNamespace(word=word,version=g['version'],operation_id=uuid4()))
with engine.connect() as c:
    ids=c.execute(select(Chest.id).where(Chest.user_id==user).order_by(Chest.level)).scalars().all()
for index,chest in enumerate(ids[4:]):
    with patch('backend.app.chest_service.roll_prize',return_value={'kind':'skin','coins':0,'rarity':'very_rare','title':'skin'}),patch('backend.app.chest_service.secrets.choice',side_effect=lambda skins,index=index:skins[index]):
        with engine.connect().execution_options(sqlite_immediate=True) as c,c.begin():
            open_chest(c,user,chest,str(uuid4()))
print(json.dumps(ids[:4]))
engine.dispose()`
    const result = await promisify(execFile)(python, ['-c', source, path.join(directory, 'test.db')], { windowsHide: true })
    return JSON.parse(result.stdout)
  }
  const prepareLeaderboards = async () => {
    await promisify(execFile)(python, [path.join(root, 'tests/leaderboard_fixtures.py'), path.join(directory, 'test.db')],
      { windowsHide: true })
  }
  const updateBuild = async (suffix) => {
    const worker = path.join(testFrontend, 'sw.js')
    const source = await readFile(worker, 'utf8')
    await writeFile(worker, source.replace(/word-guess-shell-[^']+/, `word-guess-shell-test-${suffix}`))
  }
  const restoreDatabase = async () => {
    const { restoreBrowserDatabase } = await import('./browser_restore.mjs')
    return restoreBrowserDatabase({ python, directory, env, start, freePort, waitFor })
  }
  await send('Page.enable')
  await send('Network.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url })
  if (process.argv.includes('--acceptance')) {
    const { acceptanceScenario } = await import('./acceptance_scenario.mjs')
    await acceptanceScenario({ evaluate, send, text, click, fill, setAnswer, restoreDatabase, directory, url, waitFor })
  } else if (pwaTest || process.argv.includes('--audio')) {
    const { platformScenario } = await import('./platform_scenario.mjs')
    await platformScenario({ evaluate, send, text, click, fill, setAnswer, updateBuild, directory, url, waitFor, pwaTest })
  } else if (process.argv.includes('--leaderboards')) {
    const { leaderboardsScenario } = await import('./leaderboards_scenario.mjs')
    await leaderboardsScenario({ evaluate, send, text, click, fill, setAnswer, prepareLeaderboards, directory, url, waitFor })
  } else if (process.argv.includes('--chests')) {
    const { chestScenario } = await import('./chests_scenario.mjs')
    await chestScenario({ evaluate, send, text, click, fill, setAnswer, prepareChests, directory, url, waitFor })
  } else if (process.argv.includes('--campaign')) {
    const { campaignScenario } = await import('./campaign_scenario.mjs')
    await campaignScenario({ evaluate, send, text, click, fill, setAnswer, directory, url, waitFor })
  } else if (process.argv.includes('--economy')) {
    const { economyScenario } = await import('./economy_scenario.mjs')
    await economyScenario({ evaluate, send, text, click, fill, setAnswer, directory, url, waitFor })
  } else if (process.argv.includes('--games')) {
    const { gameScenario } = await import('./game_scenario.mjs')
    await gameScenario({ evaluate, send, text, click, fill, setAnswer, directory, url, waitFor })
  } else {
  await text('Создать аккаунт')
  console.log('Guest page ready')
  await fill('display_name', 'Алиса')
  await fill('login', 'alice_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Алиса, рады видеть вас.')
  console.log('Registration passed')
  assert.equal(await evaluate('document.querySelectorAll("article").length'), 4)
  assert(await evaluate('Array.from(document.querySelectorAll("a")).some(a => a.textContent === "Играть" && a.getAttribute("href") === "/#modes-heading")'))
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
  }
  assert(server.exitCode === null, server.log)
  const scenario = process.argv.includes('--acceptance') ? 'acceptance' : pwaTest ? 'PWA/audio'
    : process.argv.includes('--audio') ? 'audio' : process.argv.includes('--leaderboards') ? 'leaderboards'
    : process.argv.includes('--chests') ? 'chests' : process.argv.includes('--campaign') ? 'campaign'
    : process.argv.includes('--economy') ? 'economy' : process.argv.includes('--games') ? 'games' : 'account'
  console.log(`PASS ${process.argv.includes('--dev') ? 'Vite proxy' : 'production'}: ${scenario} scenario`)
  console.log(`Screenshots: ${directory}`)
} catch (error) {
  if (send && socket?.readyState === WebSocket.OPEN) {
    try {
      const result = await send('Runtime.evaluate', { expression: 'document.body.innerText', returnByValue: true })
      console.error(result.result.value)
      const worker = await send('Runtime.evaluate', { returnByValue: true, awaitPromise: true,
        expression: `navigator.serviceWorker?.getRegistration().then(r=>JSON.stringify({secure:isSecureContext,controlled:!!navigator.serviceWorker.controller,
          active:r?.active?.state,waiting:r?.waiting?.state,installing:r?.installing?.state}))` })
      console.error('Worker state:', worker.result.value)
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
