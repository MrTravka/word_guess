import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

export async function campaignScenario({ evaluate, send, text, click, fill, setAnswer, directory, url, waitFor }) {
  const game = () => evaluate(`fetch('/api/games?mode=campaign').then(r => r.json())`)
  const map = () => evaluate(`fetch('/api/campaign').then(r => r.json())`)
  const navigate = async (route) => send('Page.navigate', { url: url + route })
  const screenshot = async (name) => writeFile(path.join(directory, name),
    Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  const press = async (key) => {
    await evaluate('document.activeElement?.blur()')
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
  }
  const dropWinResponse = () => evaluate(`(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (String(args[0]).endsWith('/guesses') && !window.lostCampaignWin) {
        window.lostCampaignWin = true;
        throw new TypeError('simulated lost response');
      }
      return response;
    };
  })()`)

  await text('Создать аккаунт')
  await fill('display_name', 'Путешественник')
  await fill('login', 'campaign_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Играть')
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] })
  await navigate('/campaign')
  await text('Текущий уровень: 1')
  assert.equal(await evaluate('document.querySelectorAll("ol li").length'), 20)
  assert.equal(await evaluate('document.querySelectorAll("ol a").length'), 1)
  await screenshot('campaign-desktop.png')
  await click('Дальше')
  await text('Глава 2')
  assert.equal(await evaluate('document.querySelectorAll("ol a").length'), 0)
  await click('К текущей главе')
  await text('Глава 1')
  await navigate('/play/campaign')
  await text('Начать партию')
  await click('Начать партию')
  await text('Уровень 1')
  await text('Принято попыток: 0 из 6.')
  const initial = await game()
  assert.equal(initial.answer, undefined)
  await send('Page.reload')
  await text('Принято попыток: 0 из 6.')
  assert.equal((await game()).id, initial.id)
  await click('Сдаться')
  await click('Да, завершить')
  await text('Попробовать другое слово')
  const failed = await game()
  await click('Попробовать другое слово')
  await text('Принято попыток: 0 из 6.')
  const retry = await game()
  assert.notEqual(retry.id, failed.id)
  // Surrender another retry to observe its answer without reading private data.
  await click('Сдаться')
  await click('Да, завершить')
  await text('Попробовать другое слово')
  assert.notEqual((await game()).answer.word, failed.answer.word)
  await click('Попробовать другое слово')
  await text('Принято попыток: 0 из 6.')
  await setAnswer((await game()).id, 'аист')
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 900, deviceScaleFactor: 1, mobile: true })
  await send('Emulation.setEmulatedMedia', { features: [
    { name: 'prefers-color-scheme', value: 'dark' }, { name: 'prefers-reduced-motion', value: 'reduce' },
  ] })
  await dropWinResponse()
  for (const letter of 'аист') await press(letter)
  await press('Enter')
  await text('Повторить действие')
  assert.equal((await map()).current_level, 2)
  await click('Повторить действие')
  await text('Следующий уровень')
  assert.equal((await map()).current_level, 2)
  assert.equal((await game()).campaign.stars, 3)
  await click('Следующий уровень')
  await text('Уровень 2')
  await navigate('/campaign')
  await text('Текущий уровень: 2')
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  assert.equal(await evaluate('document.querySelectorAll("ol li").length'), 20)
  await screenshot('campaign-phone.png')

  // Finish through 21 using the real UI; only answers in the isolated DB are fixtures.
  await navigate('/play/campaign')
  await text('Принято попыток: 0 из 6.')
  for (let level = 2; level <= 21; level++) {
    await setAnswer((await game()).id, 'аист')
    for (const letter of 'аист') await press(letter)
    await press('Enter')
    await text('Следующий уровень')
    if (level % 10 === 0) await text(`Сундук за уровень ${level} сохранён!`)
    if (level < 21) {
      await click('Следующий уровень')
      await waitFor(async () => (await game()).status === 'active', `level ${level + 1} started`)
      await text('Принято попыток: 0 из 6.')
    }
  }
  assert.equal((await map()).current_level, 22)
  assert.equal((await map()).chests, 2)
  await send('Page.reload')
  await text('Следующий уровень')
  assert.equal((await map()).chests, 2)
  await navigate('/campaign')
  await text('Текущий уровень: 22')
  await text('Сундуков получено: 2')
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  await screenshot('campaign-chapter-two.png')
  console.log('Campaign map, pagination, retry word, reload, lost win response, levels 1–21 and two chests PASS')
}
