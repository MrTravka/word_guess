import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

export async function acceptanceScenario({ evaluate, send, text, click, fill, setAnswer, restoreDatabase, directory, url, waitFor }) {
  const api = (route) => evaluate(`fetch('/api${route}').then(r=>r.json())`)
  const navigate = (route) => send('Page.navigate', { url: url + route })
  const type = async (word) => {
    await evaluate('document.activeElement?.blur()')
    for (const key of [...word, 'Enter']) {
      await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
    }
  }
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 740, deviceScaleFactor: 1, mobile: true })
  await send('Emulation.setEmulatedMedia', { features: [
    { name: 'prefers-color-scheme', value: 'dark' }, { name: 'prefers-reduced-motion', value: 'reduce' },
  ] })
  await text('Создать аккаунт')
  await fill('display_name', 'Приёмка')
  await fill('login', 'acceptance_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Играть')
  await navigate('/play/4')
  await text('Начать партию')
  await click('Начать партию')
  await text('Принято попыток: 0 из 6.')
  await setAnswer((await api('/games?mode=4')).id, 'аист')
  await type('аист')
  await text('Слово найдено!')
  assert.equal((await api('/inventory')).coins, 180)
  await navigate('/shop')
  await text('Купить за 60')
  await waitFor(() => evaluate(`!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Купить за 60').disabled`), 'shop ready')
  await click('Купить за 60')
  await text('Списано 60 монет.')
  assert.equal((await api('/inventory')).inventory.random_letter, 2)
  await navigate('/campaign')
  await text('Текущий уровень: 1')
  await evaluate(`document.querySelector('a[href="/play/campaign"]').click()`)
  await text('Начать партию')
  await click('Начать партию')
  for (let level = 1; level <= 10; level++) {
    await text('Принято попыток: 0 из 6.')
    await setAnswer((await api('/games?mode=campaign')).id, 'аист')
    await type('аист')
    await text('Следующий уровень')
    if (level < 10) await click('Следующий уровень')
  }
  await text('Сундук за уровень 10 сохранён!')
  const chestId = (await api('/games?mode=campaign')).campaign.chest_id
  await evaluate(`document.querySelector('a[href="/chests/${chestId}"]').click()`)
  await text('Открыть сундук')
  await click('Открыть сундук')
  await text('Ваша награда:')
  const opening = (await api(`/chests/${chestId}`)).chest.opening
  const inventory = await api('/inventory')
  assert.equal(inventory.coins, 420 + opening.result.prize.coins)
  assert.deepEqual(inventory.points, { '4': 120, '5': 0, '6': 0, campaign: 1200 })
  await navigate('/leaderboards?mode=campaign')
  await text('Ваше место: 1')
  await text('Очки: 1200')
  assert.equal((await api('/leaderboards?mode=campaign')).statistics.wins, 10)
  assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'))
  await writeFile(path.join(directory, 'acceptance-leaderboard.png'), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))

  await navigate('/play/6')
  await text('Начать партию')
  await click('Начать партию')
  await text('Принято попыток: 0 из 6.')
  await setAnswer((await api('/games?mode=6')).id, 'ворона')
  await type('корова')
  await text('Принято попыток: 1 из 6.')
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.startsWith('Случайная буква')).click()`)
  await text('Применить подсказку')
  await click('Применить подсказку')
  await waitFor(async () => (await api('/games?mode=6')).version === 2, 'hint saved')
  const active = await api('/games?mode=6')
  const savedWallet = await api('/inventory')
  const savedRating = await api('/leaderboards?mode=campaign')
  const restored = await restoreDatabase()
  await send('Page.navigate', { url: restored + '/play/6' })
  await text('Принято попыток: 1 из 6.')
  assert.deepEqual(await api('/games?mode=6'), active)
  assert.deepEqual(await api('/inventory'), savedWallet)
  assert.deepEqual(await api('/leaderboards?mode=campaign'), savedRating)
  assert.deepEqual((await api(`/chests/${chestId}`)).chest.opening, opening)
  await evaluate(`fetch('/api/chests/${chestId}/open',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'word_guess'},
    body:JSON.stringify({operation_id:crypto.randomUUID()})}).then(r=>{if(!r.ok)throw Error('replay failed')})`)
  assert.deepEqual(await api('/inventory'), savedWallet)
  assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'))
  console.log('Acceptance PASS: registration → win/reward → shop → campaign → chest → ranking → live backup/restore → active hint/session recovery')
}
