import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'
import { audioProbe, analyseAudio } from './audio_probe.mjs'

export async function audioScenario({ evaluate, send, text, click, fill, setAnswer, directory, url, waitFor }) {
  await send('Page.addScriptToEvaluateOnNewDocument', { source: audioProbe })
  await evaluate(audioProbe)
  const api = (route) => evaluate(`fetch('/api${route}').then(r=>r.json())`)
  await text('Создать аккаунт')
  await fill('display_name', 'Слушатель')
  await fill('login', 'platform_browser')
  await fill('password', 'browser-password-123')
  await click('Создать аккаунт')
  await text('Слушатель, рады видеть вас.')
  assert.equal(await evaluate('document.querySelectorAll("audio").length'), 0)
  assert.equal(await evaluate('window.audioContexts.length'), 0)
  await click('Настройки')
  await text('Музыка и звуки')
  await waitFor(() => evaluate(`!document.querySelector('input[type="checkbox"]').disabled`), 'audio preferences loaded')
  await evaluate(`document.querySelectorAll('input[type="checkbox"]')[0].click()`, true)
  await evaluate(`document.querySelectorAll('input[type="checkbox"]')[1].click()`, true)
  await evaluate(`(() => { const input=document.querySelector('input[aria-label="Громкость музыки"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'30');
    input.dispatchEvent(new Event('input',{bubbles:true})); })()`, true)
  await click('Сохранить звук')
  await text('Настройки звука сохранены.')
  assert.deepEqual(await api('/settings/audio'), { music_enabled: true, sounds_enabled: true, music_volume: 30, sounds_volume: 35 })
  await waitFor(() => evaluate(`document.querySelector('audio')?.paused===false&&document.querySelector('audio').currentTime>0.05`), 'music playing after gesture')
  assert.equal(await evaluate('document.querySelector("audio").loop'), true)
  assert.equal(await evaluate('window.audioContexts.length'), 1)
  assert.equal(await evaluate('window.mediaSourceCount'), 1)
  await waitFor(() => evaluate('Math.abs(window.musicGain.gain.value-0.3)<0.01'), 'music volume ramp')
  await click('Проверить звуки')
  assert(await evaluate('window.effectCount>=3'))
  // Visibility handler pauses the same element and resumes its current position.
  await evaluate(`window.testHidden=true;Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.testHidden});document.dispatchEvent(new Event('visibilitychange'))`)
  assert(await evaluate('document.querySelector("audio").paused'))
  await evaluate(`window.testHidden=false;document.dispatchEvent(new Event('visibilitychange'))`)
  await waitFor(() => evaluate('document.querySelector("audio").paused===false'), 'music resumed')
  const analysed = await evaluate(analyseAudio)
  await writeFile(path.join(directory, 'audio-report.json'), JSON.stringify(analysed.report, null, 2))
  await writeFile(path.join(directory, 'ost-seam.wav'), Buffer.from(analysed.seam_wav, 'base64'))
  assert(analysed.report.duration > 10 && analysed.report.rms > 0)
  await evaluate(`document.querySelector('audio').currentTime=document.querySelector('audio').duration-0.15`)
  await waitFor(() => evaluate('document.querySelector("audio").currentTime<2&&!document.querySelector("audio").paused'), 'original track loops')
  await click('На главную')
  await evaluate(`document.querySelector('a[href="/play/6"]').click()`)
  await text('Начать партию')
  await click('Начать партию')
  await text('Принято попыток: 0 из 6.')
  const game = await api('/games?mode=6')
  await setAnswer(game.id, 'ворона')
  const effectsBefore = await evaluate('window.effectCount')
  for (const key of 'корова') {
    await evaluate('document.activeElement?.blur()')
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key })
  }
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter' })
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter' })
  await text('Принято попыток: 1 из 6.')
  assert(await evaluate(`window.effectCount>${effectsBefore}`))
  assert.equal(await evaluate('document.querySelectorAll("audio").length'), 1)
  assert.equal(await evaluate('window.mediaSourceCount'), 1)
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 740, deviceScaleFactor: 1, mobile: true })
  await send('Emulation.setEmulatedMedia', { features: [
    { name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' },
  ] })
  const contrast = await evaluate(`(() => {
    const rgb=s=>s.match(/[\\d.]+/g).slice(0,3).map(n=>+n/255);
    const lum=s=>rgb(s).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
    const nodes=[...document.querySelectorAll('[data-word-cell][data-mark],[class*="secondary"]')];
    return nodes.map(node=>{const s=getComputedStyle(node);return (Math.max(lum(s.color),lum(s.backgroundColor))+.05)/(Math.min(lum(s.color),lum(s.backgroundColor))+.05)});
  })()`)
  assert(contrast.every(value => value >= 4.5), `contrast ${JSON.stringify(contrast)}`)
  assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'))
  await writeFile(path.join(directory, 'game-audio-phone.png'), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  await send('Page.reload')
  await text('Принято попыток: 1 из 6.')
  assert.equal((await api('/games?mode=6')).id, game.id)
  // Saved enabled settings do not bypass autoplay rules after reload.
  assert.equal(await evaluate('document.querySelectorAll("audio").length'), 0)
  assert.equal(await evaluate('window.audioContexts.length'), 0)
  console.log(`Audio PASS: opt-in, preferences, single player, volume, visibility, effects and ${analysed.report.duration.toFixed(2)} s loop`)
  return { game, api }
}
