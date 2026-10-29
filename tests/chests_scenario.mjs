import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

export async function chestScenario({ evaluate, send, text, click, fill, setAnswer, prepareChests, directory, url, waitFor }) {
  const api = (route) => evaluate(`fetch('/api${route}').then(r => r.json())`)
  const navigate = async (route) => send('Page.navigate', { url: url + route })
  const screenshot = async (name) => writeFile(path.join(directory, name),
    Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  const press = async (key) => {
    await evaluate('document.activeElement?.blur()')
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
  }
  const colors = () => evaluate(`Object.fromEntries(['correct','present','absent'].map(mark => {
    const cell=document.querySelector('[aria-label^="Поле"] [data-mark="'+mark+'"]');
    const s=getComputedStyle(cell); return [mark,[s.backgroundColor,s.color]];
  }))`)
  const media = (theme, reduced = false) => send('Emulation.setEmulatedMedia', { features: [
    { name: 'prefers-color-scheme', value: theme }, { name: 'prefers-reduced-motion', value: reduced ? 'reduce' : 'no-preference' },
  ] })

  await text('Создать аккаунт')
  await fill('display_name', 'Коллекционер')
  await fill('login', 'chests_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Коллекционер, рады видеть вас.')
  const ids = await prepareChests()
  let expectedCoins = (await api('/inventory')).coins
  await media('light')
  await navigate('/chests')
  await text('Неоткрытые 4')
  await evaluate(`document.querySelector('summary').click()`)
  await text('50%')
  await text('350 монет')
  assert.equal(await evaluate('document.querySelectorAll("tbody tr").length'), 6)
  await screenshot('chests-light.png')

  await navigate(`/chests/${ids[0]}`)
  await text('Открыть сундук')
  await click('Открыть сундук')
  await text('Пропустить')
  const first = (await api(`/chests/${ids[0]}`)).chest.opening
  expectedCoins += first.result.prize.coins
  await screenshot('chest-reel.png')
  await click('Пропустить')
  await text(`Ваша награда: ${first.result.prize.title}`)
  assert.equal((await api('/inventory')).coins, expectedCoins)
  await send('Page.reload')
  await text(`Ваша награда: ${first.result.prize.title}`)
  assert.deepEqual((await api(`/chests/${ids[0]}`)).chest.opening, first)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Открыть сундук')`), false)

  await media('dark', true)
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 900, deviceScaleFactor: 1, mobile: true })
  await navigate(`/chests/${ids[1]}`)
  await text('Открыть сундук')
  await evaluate(`(() => { const original=fetch.bind(window); window.fetch=async(...args)=>{
    const response=await original(...args);
    if(String(args[0]).endsWith('/open')&&!window.lostOpen){window.lostOpen=true;throw new TypeError('lost opening response')}
    return response;
  }})()`)
  await click('Открыть сундук')
  await text('Восстановить открытие')
  const second = (await api(`/chests/${ids[1]}`)).chest.opening
  expectedCoins += second.result.prize.coins
  await click('Восстановить открытие')
  await text(`Ваша награда: ${second.result.prize.title}`)
  assert.deepEqual((await api(`/chests/${ids[1]}`)).chest.opening, second)
  assert.equal((await api('/inventory')).coins, expectedCoins)
  assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
  await screenshot('chest-result-phone.png')

  await media('dark')
  await navigate(`/chests/${ids[2]}`)
  await text('Открыть сундук')
  await click('Открыть сундук')
  await text('Пропустить')
  const third = (await api(`/chests/${ids[2]}`)).chest.opening
  expectedCoins += third.result.prize.coins
  await navigate('/campaign')
  await text('Текущий уровень: 101')
  await navigate(`/chests/${ids[2]}`)
  await text(`Ваша награда: ${third.result.prize.title}`)
  assert.equal((await api('/inventory')).coins, expectedCoins)

  await navigate(`/chests/${ids[3]}`)
  await text('Открыть сундук')
  await click('Открыть сундук')
  await text('Пропустить')
  const fourth = (await api(`/chests/${ids[3]}`)).chest.opening
  expectedCoins += fourth.result.prize.coins
  // Let the final spin finish; verify the pointer lands on the saved winner.
  const distance = await evaluate(`(() => {
    const track=document.querySelector('[class*="track"]');
    track.getAnimations()[0].currentTime=4500;
    const winner=track.children[${fourth.result.winner_index}].getBoundingClientRect();
    const viewport=track.parentElement.getBoundingClientRect();
    return {distance:Math.abs((winner.left+winner.right)/2-(viewport.left+viewport.right)/2),
      winner:[winner.left,winner.width], viewport:[viewport.left,viewport.width],
      transform:getComputedStyle(track).transform, width:track.offsetWidth,
      gap:getComputedStyle(track).gap};
  })()`)
  assert(distance.distance < 2, `saved winner centered under the pointer: ${JSON.stringify(distance)}`)
  await text(`Ваша награда: ${fourth.result.prize.title}`)
  assert.equal((await api('/inventory')).coins, expectedCoins)
  await navigate('/chests')
  await text('Неоткрытые 0')
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.startsWith('История')).click()`)
  await text('Посмотреть награду')
  assert.equal((await api('/chests?state=opened')).items.length, 10)
  await screenshot('chests-history-phone.png')

  // All six earned cosmetics came from deterministic fixture openings through real services.
  await navigate('/play/6')
  await text('Начать партию')
  await click('Начать партию')
  await text('Принято попыток: 0 из 6.')
  await setAnswer((await api('/games?mode=6')).id, 'ворона')
  for (const letter of 'корова') await press(letter)
  await press('Enter')
  await text('Принято попыток: 1 из 6.')
  await waitFor(() => evaluate(`document.querySelector('[data-word-cell][data-mark="correct"]')!==null`), 'feedback visible')
  const skins = (await api('/collection')).skins
  assert.equal(skins.length, 6)
  assert(skins.every(skin => skin.owned))
  for (const theme of ['light', 'dark']) {
    await media(theme, true)
    await navigate('/collection')
    await text('Базовое оформление')
    await click('Базовое оформление')
    await text('Оформление сохранено.')
    await navigate('/play/6')
    await text('Принято попыток: 1 из 6.')
    const baseline = await colors()
    for (const skin of skins) {
      await navigate('/collection')
      await text(`Применить «${skin.title}»`)
      await click(`Применить «${skin.title}»`)
      await text('Оформление сохранено.')
      await navigate('/play/6')
      await text('Принято попыток: 1 из 6.')
      await waitFor(() => evaluate(`document.querySelector('[data-skin="${skin.id}"]')!==null`), `skin ${skin.id} applied`)
      assert.deepEqual(await colors(), baseline, `feedback colors unchanged: ${theme}/${skin.id}`)
      assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'))
      if (skin.id === 'orbit') await screenshot(`skin-orbit-${theme}.png`)
    }
  }
  await send('Page.reload')
  await text('Принято попыток: 1 из 6.')
  assert.equal((await api('/collection')).selected_skin, skins.at(-1).id)
  await navigate('/collection')
  await text('Коллекция')
  await text('Выбран')
  await screenshot('collection-phone.png')
  console.log('Chest odds, spin/skip/close/reload, lost response, history, all six skins in both themes and 360 px PASS')
}
