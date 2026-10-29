import assert from 'node:assert/strict'

export async function pwaScenario({ evaluate, send, text, click, updateBuild, url, waitFor, game, api }) {
  await waitFor(() => evaluate(`Boolean(navigator.serviceWorker.controller)`), 'service worker controls the app')
  const manifest = await send('Page.getAppManifest')
  assert.equal(manifest.errors.length, 0)
  const installability = await send('Page.getInstallabilityErrors')
  assert.deepEqual(installability.installabilityErrors, [])
  assert.equal(JSON.parse(manifest.data).display, 'standalone')
  async function cacheFiles() {
    return evaluate(`(async()=>{const keys=await caches.keys();return (await Promise.all(keys.map(async key=>(await (await caches.open(key)).keys()).map(r=>new URL(r.url).pathname)))).flat()})()`)
  }
  assert((await cacheFiles()).includes('/index.html'))
  assert((await cacheFiles()).every(file => !file.startsWith('/api/') && !file.startsWith('/audio/')))
  await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 })
  await send('Page.reload')
  await text('Нет связи с сервером.')
  assert(await evaluate('document.getElementById("root").children.length>0'))
  assert.equal(await evaluate(`document.body.innerText.includes('Принято попыток: 1 из 6.')`), false)
  await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 })
  await evaluate(`window.dispatchEvent(new Event('online'))`)
  await text('Принято попыток: 1 из 6.')
  assert.equal((await api('/games?mode=6')).id, game.id)
  // A broken response body must keep the original operation key for recovery.
  await evaluate(`(() => {const original=fetch.bind(window);window.fetch=async(...args)=>{
    const response=await original(...args);
    if(String(args[0]).endsWith('/guesses')&&!window.brokenBody){window.brokenBody=true;return new Response('{',{status:200,headers:{'content-type':'application/json'}})}
    return response;
  }})()`)
  for (const key of 'молоко') {
    await evaluate('document.activeElement?.blur()')
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
  }
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter' })
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter' })
  await text('Повторить действие')
  await click('Повторить действие')
  await text('Принято попыток: 2 из 6.')
  assert.equal((await api('/games?mode=6')).guesses.length, 2)
  await updateBuild('2')
  await evaluate(`navigator.serviceWorker.getRegistration().then(r=>r.update())`)
  await text('Доступна новая версия.')
  assert(await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Обновить приложение').disabled`))
  await evaluate(`document.querySelector('a[href="/#modes-heading"]').click()`)
  await text('Четыре пути к ответу')
  await waitFor(() => evaluate(`!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Обновить приложение').disabled`), 'update enabled outside the game')
  await click('Настройки')
  await text('Музыка и звуки')
  await waitFor(() => evaluate(`!document.querySelector('input[type="checkbox"]').disabled`), 'audio loaded')
  await evaluate(`(() => {const original=fetch.bind(window);window.fetch=async(...args)=>{
    const response=await original(...args);
    if(String(args[0]).endsWith('/settings/audio')&&args[1]?.method==='PUT')await new Promise(resolve=>window.releaseSave=resolve);
    return response;
  }})()`)
  await click('Сохранить звук')
  await waitFor(() => evaluate(`typeof window.releaseSave==='function'`), 'save response held')
  assert(await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Обновить приложение').disabled`))
  await evaluate('window.releaseSave()')
  await text('Настройки звука сохранены.')
  await evaluate(`window.otherWindow=window.open('/','pwa-other');true`, true)
  await waitFor(() => evaluate(`window.otherWindow?.document.readyState==='complete'`), 'second window ready')
  await send('Page.bringToFront')
  await click('Обновить приложение')
  await text('Закройте другие окна игры')
  await evaluate('window.otherWindow.close()')
  await click('Обновить приложение')
  await text('Слушатель, рады видеть вас.')
  await waitFor(() => evaluate(`caches.keys().then(keys=>keys.includes('word-guess-shell-test-2'))`), 'new cache active')
  assert.equal(await evaluate(`document.body.innerText.includes('Доступна новая версия.')`), false)
  assert((await cacheFiles()).every(file => !file.startsWith('/api/')))
  await send('Page.navigate', { url: url + '/play/6' })
  await text('Принято попыток: 2 из 6.')
  assert.equal((await api('/games?mode=6')).id, game.id)
  assert.deepEqual(await api('/settings/audio'), { music_enabled: true, sounds_enabled: true, music_volume: 30, sounds_volume: 35 })
  console.log('PWA PASS: installability, private cache boundary, offline shell, game recovery, broken body, update gating and multiple windows')
}
