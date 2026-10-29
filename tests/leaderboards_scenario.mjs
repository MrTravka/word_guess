import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

export async function leaderboardsScenario({ evaluate, send, text, click, fill, setAnswer, prepareLeaderboards, directory, url, waitFor }) {
  const api = (route) => evaluate(`fetch('/api${route}').then(r=>r.json())`)
  const navigate = (route) => send('Page.navigate', { url: url + route })
  const screenshot = async (name) => writeFile(path.join(directory, name),
    Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  const press = async (key) => {
    await evaluate('document.activeElement?.blur()')
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
  }
  const mode = async (title) => {
    await click(title)
    await waitFor(() => evaluate(`document.querySelector('caption')?.textContent.startsWith(${JSON.stringify(title)})`), title)
  }
  const ownRow = () => evaluate(`document.querySelector('tr[data-self="true"]')?.textContent`)

  await text('Создать аккаунт')
  await fill('display_name', 'Исследователь')
  await fill('login', 'leaderboards_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Исследователь, рады видеть вас.')
  await evaluate(`document.querySelector('a[href="/leaderboards"]').click()`)
  await text('Ваше место: пока нет')
  await text('Пока нет побед в этом режиме.')
  await prepareLeaderboards()
  await send('Page.reload')
  await text('Ваше место: 26')
  assert.equal(await evaluate('document.querySelectorAll("tbody tr").length'), 20)
  assert.equal(await ownRow(), undefined)
  const five = await api('/leaderboards?mode=5')
  assert.equal(five.self.points, 100)
  assert.equal(five.statistics.losses, 1)
  assert.equal(five.statistics.win_rate, 50)
  assert.equal(five.statistics.average_attempts, 3)
  assert.equal(await evaluate('document.querySelectorAll("tbody img").length'), 0)
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] })
  await screenshot('leaderboards-desktop.png')
  await click('К моему месту')
  await text('Страница 2 из 2')
  assert.equal(await evaluate('document.querySelectorAll("tbody tr").length'), 6)
  assert((await ownRow()).includes('Исследователь'))
  await send('Page.reload')
  await text('Страница 2 из 2')
  assert((await ownRow()).includes('Исследователь'))
  await click('К началу рейтинга')
  await text('Страница 1 из 2')
  await mode('4 буквы')
  assert.equal((await api('/leaderboards?mode=4')).self.points, 60)
  assert(await evaluate(`new URL(location.href).searchParams.get('page')==='1'`))
  await mode('6 букв')
  await text('Ваше место: пока нет')
  await mode('Кампания')
  await text('Уровень: 2')
  assert.equal((await api('/leaderboards?mode=campaign')).self.points, 20)
  assert.equal(await evaluate(`document.querySelectorAll('thead th').length`), 5)

  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 900, deviceScaleFactor: 1, mobile: true })
  for (const theme of ['light', 'dark']) {
    await send('Emulation.setEmulatedMedia', { features: [
      { name: 'prefers-color-scheme', value: theme }, { name: 'prefers-reduced-motion', value: 'reduce' },
    ] })
    assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
    await screenshot(`leaderboards-campaign-${theme}.png`)
  }
  await mode('5 букв')
  await evaluate(`document.querySelector('a[href="#statistics-heading"]').click()`)
  await text('Ваша статистика')
  assert.equal(await evaluate('document.querySelectorAll("ol li").length'), 6)
  assert.equal(await evaluate(`document.querySelector('li[aria-label="Попыток: 3. Побед: 1."]')!==null`), true)
  await screenshot('statistics-phone.png')

  // The cached six-letter rating must update after a real win and a lost response.
  await navigate('/play/6')
  await text('Начать партию')
  await click('Начать партию')
  await text('Принято попыток: 0 из 6.')
  await setAnswer((await api('/games?mode=6')).id, 'ворона')
  await evaluate(`(() => { const original=fetch.bind(window); window.fetch=async(...args)=>{
    const response=await original(...args);
    if(String(args[0]).endsWith('/guesses')&&!window.lostRankWin){window.lostRankWin=true;throw new TypeError('lost win response')}
    return response;
  }})()`)
  for (const letter of 'ворона') await press(letter)
  await press('Enter')
  await text('Повторить действие')
  await click('Повторить действие')
  await text('Слово найдено!')
  await evaluate(`Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='Моя статистика').click()`)
  await text('Ваше место: 26')
  await text('Очки: 180')
  await waitFor(() => evaluate(`document.activeElement?.id==='statistics-heading'`), 'statistics heading focused')
  const six = await api('/leaderboards?mode=6')
  assert.equal(six.self.points, 180)
  assert.equal(six.statistics.games, 1)
  assert.equal(six.statistics.average_attempts, 1)
  assert.equal((await api('/leaderboards?mode=5')).self.points, 100)

  await send('Network.setBlockedURLs', { urls: ['*api/leaderboards*'] })
  await navigate('/leaderboards?mode=4')
  await text('Повторить')
  await send('Network.setBlockedURLs', { urls: [] })
  await click('Повторить')
  await text('Ваше место: 26')
  assert.equal((await api('/leaderboards?mode=4')).self.points, 60)
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  await screenshot('leaderboards-recovered.png')
  console.log('Four ratings, own place outside top, pagination, metrics, win/retry refresh, privacy, long names and both themes PASS')
}
