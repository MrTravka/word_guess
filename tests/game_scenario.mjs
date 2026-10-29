import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

export async function gameScenario({ evaluate, send, text, click, fill, setAnswer, directory, url, waitFor }) {
  const latest = (mode = '5') => evaluate(`fetch('/api/games?mode=${mode}').then(r => r.json())`)
  const waitVersion = (version, mode = '5') => waitFor(async () => (await latest(mode))?.version === version, `version ${version}`)
  const physical = async (word) => {
    await evaluate('document.activeElement?.blur()')
    for (const key of word) {
      await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
    }
  }
  const submit = async () => {
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', windowsVirtualKeyCode: 13 })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', windowsVirtualKeyCode: 13 })
  }
  const keyboardReady = () => waitFor(() => evaluate(`!document.querySelector('button[aria-label="Отправить слово"]').disabled`), 'keyboard unlocked')
  const screenWord = async (word) => {
    for (const letter of word) await evaluate(`document.querySelector('button[aria-label="${letter.toUpperCase()}"], button[aria-label^="${letter.toUpperCase()}:"]').click()`)
  }
  const screenSubmit = () => evaluate(`document.querySelector('button[aria-label="Отправить слово"]').click()`)
  const openMode = async (mode) => {
    await send('Page.navigate', { url: `${url}/play/${mode}` })
    await text('Начать партию')
    await click('Начать партию')
    await text('Принято попыток: 0 из 6.')
  }
  const screenshot = async (name) => writeFile(path.join(directory, name), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))

  await text('Создать аккаунт')
  await fill('display_name', 'Игрок')
  await fill('login', 'game_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Играть')
  await openMode('5')
  const game = await latest()
  assert(!('answer' in game))
  await setAnswer(game.id, 'касса')
  await physical('ааааа')
  await submit()
  await text('Такого существительного нет в словаре.')
  assert.equal((await latest()).version, 0)
  for (let i = 0; i < 5; i++) await physical(['Backspace'])
  await physical('маска')
  await submit()
  await submit() // Double Enter cannot add a second row.
  await waitVersion(1)
  await keyboardReady()
  let data = await latest()
  assert.deepEqual(data.guesses[0].marks, ['absent', 'correct', 'correct', 'present', 'correct'])
  assert.equal(data.guesses.length, 1)
  await send('Page.reload')
  await text('Принято попыток: 1 из 6.')
  assert(await evaluate(`document.querySelector('[aria-label^="Попытка 1:"]').getAttribute('aria-label').includes('МАСКА')`))
  await physical('касса')
  await submit()
  await text('Слово найдено!')
  assert(await evaluate('document.body.innerText.includes("КАССА")'))
  assert.equal((await latest()).status, 'won')
  assert(await evaluate(`Array.from(document.querySelectorAll('a')).some(a => a.textContent.includes('Викисловарь'))`))
  await send('Page.reload')
  await text('Слово найдено!')
  await click('Следующее слово')
  await text('Принято попыток: 0 из 6.')
  data = await latest()
  assert.notEqual(data.id, game.id)
  await setAnswer(data.id, 'касса')
  // Lose only the response, after the real server has accepted the request.
  await evaluate(`(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (String(args[0]).endsWith('/guesses') && !window.droppedGuess) {
        window.droppedGuess = true;
        throw new TypeError('simulated lost response');
      }
      return response;
    };
  })()`)
  await screenWord('маска')
  await screenSubmit()
  await text('Повторить действие')
  await click('Повторить действие')
  await waitVersion(1)
  await keyboardReady()
  assert.equal((await latest()).guesses.length, 1)
  await screenWord('сосна')
  await screenSubmit()
  await waitVersion(2)
  await keyboardReady()
  for (const [index, word] of ['слово', 'лампа', 'банка', 'атака'].entries()) {
    await physical(word)
    await submit()
    await waitVersion(index + 3)
    if (word !== 'атака') await keyboardReady()
  }
  await text('В этот раз не получилось')
  assert.equal((await latest()).guesses.length, 6)
  await screenshot('game-result-desktop.png')

  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 900, deviceScaleFactor: 1, mobile: true })
  await send('Emulation.setEmulatedMedia', { features: [
    { name: 'prefers-color-scheme', value: 'dark' }, { name: 'prefers-reduced-motion', value: 'reduce' },
  ] })
  await openMode('6')
  await setAnswer((await latest('6')).id, 'ворона')
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  await screenshot('game-six-phone.png')
  await screenWord('машина')
  await screenSubmit()
  await waitVersion(1, '6')
  await keyboardReady()
  await click('Сдаться')
  await click('Продолжить играть')
  assert.equal((await latest('6')).status, 'active')
  await click('Сдаться')
  await click('Да, завершить')
  await text('Партия завершена')
  assert.equal((await latest('6')).status, 'surrendered')
  assert.equal((await latest()).status, 'lost')

  await openMode('4')
  await setAnswer((await latest('4')).id, 'елка')
  await physical('ёлка')
  await submit()
  await text('Слово найдено!')
  assert.equal((await latest('4')).status, 'won')
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  await screenshot('game-four-win-phone.png')
  console.log('Three lengths, repeated letters, both keyboards, double Enter, restore, lost-response retry, win/loss/surrender and 360px PASS')
}
