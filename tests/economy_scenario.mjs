import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

export async function economyScenario({ evaluate, send, text, click, fill, setAnswer, directory, url, waitFor }) {
  const inventory = () => evaluate(`fetch('/api/inventory').then(r => r.json())`)
  const game = (mode = '5') => evaluate(`fetch('/api/games?mode=${mode}').then(r => r.json())`)
  const press = async (key) => {
    await evaluate('document.activeElement?.blur()')
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
  }
  const choose = (prefix) => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.startsWith(${JSON.stringify(prefix)})).click()`)
  const waitVersion = (version, mode = '5') => waitFor(async () => (await game(mode))?.version === version, `game version ${version}`)
  const dropResponse = (suffix, marker) => evaluate(`(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (String(args[0]).endsWith(${JSON.stringify(suffix)}) && !window[${JSON.stringify(marker)}]) {
        window[${JSON.stringify(marker)}] = true;
        throw new TypeError('simulated lost response');
      }
      return response;
    };
  })()`)
  const navigate = async (route) => { await send('Page.navigate', { url: url + route }) }
  const screenshot = async (name) => writeFile(path.join(directory, name), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))

  await text('Создать аккаунт')
  await fill('display_name', 'Игрок')
  await fill('login', 'economy_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Игрок, рады видеть вас.')
  assert.equal((await inventory()).coins, 150)
  assert.equal((await inventory()).inventory.random_letter, 1)
  await navigate('/shop')
  await text('Купить за 100')
  await waitFor(() => evaluate(`!Array.from(document.querySelectorAll('button')).find(b => b.textContent === 'Купить за 100').disabled`), 'shop balance ready')
  await click('Купить за 100')
  await text('Списано 100 монет.')
  assert.equal((await inventory()).coins, 50)
  await dropResponse('/purchases', 'lostPurchase')
  await click('Купить за 25')
  await text('Повторить покупку')
  assert.equal((await inventory()).coins, 25)
  await click('Повторить покупку')
  await text('Списано 25 монет.')
  assert.equal((await inventory()).coins, 25)
  assert.equal((await inventory()).inventory.eliminate, 1)
  await screenshot('shop-desktop.png')

  await navigate('/play/5')
  await text('Начать партию')
  await click('Начать партию')
  await text('Принято попыток: 0 из 6.')
  await setAnswer((await game()).id, 'касса')
  await choose('Буква на выбранном месте')
  await text('Выберите неизвестную позицию')
  await evaluate(`document.querySelector('input[name="hint-position"]').click()`)
  await click('Отмена')
  assert.equal((await inventory()).inventory.position_letter, 1)
  assert.equal((await game()).version, 0)
  await choose('Буква на выбранном месте')
  await evaluate(`document.querySelector('input[name="hint-position"]').click()`)
  await click('Применить подсказку')
  await waitVersion(1)
  await text('Подставить открытые буквы')
  assert.equal((await game()).hints.revealed['0'], 'к')
  await choose('Случайная буква')
  await click('Применить подсказку')
  await waitVersion(2)
  await choose('Убрать лишние')
  await click('Применить подсказку')
  await waitVersion(3)
  const beforeWin = await game()
  assert.equal(beforeWin.hints.uses.length, 3)
  assert.equal(beforeWin.guesses.length, 0)
  await click('Подставить открытые буквы')
  for (let position = 0; position < 5; position++) {
    if (!beforeWin.hints.revealed[String(position)]) await press('касса'[position])
  }
  await evaluate(`document.querySelector('button[aria-label="Отправить слово"]').click()`)
  await text('Слово найдено!')
  await text('63 очков')
  assert.deepEqual((await game()).reward, { points: 63, coins: 37, hints: 3 })
  assert.equal((await inventory()).coins, 62)
  await send('Page.reload')
  await text('63 очков')
  assert.equal((await inventory()).coins, 62)

  await navigate('/shop')
  await text('Купить за 60')
  await waitFor(() => evaluate(`!Array.from(document.querySelectorAll('button')).find(b => b.textContent === 'Купить за 60').disabled`), 'shop refreshed balance')
  await click('Купить за 60')
  await text('Списано 60 монет.')
  assert.equal((await inventory()).coins, 2)
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 900, deviceScaleFactor: 1, mobile: true })
  await send('Emulation.setEmulatedMedia', { features: [
    { name: 'prefers-color-scheme', value: 'dark' }, { name: 'prefers-reduced-motion', value: 'reduce' },
  ] })
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  await screenshot('shop-phone.png')
  await navigate('/play/6')
  await text('Начать партию')
  await click('Начать партию')
  await text('Принято попыток: 0 из 6.')
  await setAnswer((await game('6')).id, 'ворона')
  await dropResponse('/hints', 'lostHint')
  await choose('Случайная буква')
  await click('Применить подсказку')
  await text('Повторить действие')
  await click('Повторить действие')
  await waitVersion(1, '6')
  assert.equal((await game('6')).hints.uses.length, 1)
  assert.equal((await inventory()).inventory.random_letter, 0)
  assert.equal((await inventory()).coins, 2)
  await screenshot('hints-phone.png')
  await click('Сдаться')
  await click('Да, завершить')
  await text('Партия завершена')
  assert.equal((await inventory()).inventory.random_letter, 0)
  assert.equal((await inventory()).coins, 2)
  assert.equal((await game('6')).reward.coins, 0)
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  console.log('Starter, shop, lost purchase/hint responses, target cancellation, three hints, insertion, reward, reload and no refund PASS')
}
