import { randomUUID } from 'node:crypto'

export function createProtocol(socket, waitFor) {
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
  const command = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)) }, 10000)
    pending.set(id, { resolve, reject, timer })
    socket.send(JSON.stringify({ id, method, params }))
  })
  return async (method, params = {}) => {
    if (!['Page.navigate', 'Page.reload'].includes(method)) return command(method, params)
    const token = randomUUID()
    await command('Runtime.evaluate', { expression: `window.__navigationToken=${JSON.stringify(token)}` })
    const result = await command(method, params)
    if (result.errorText) throw new Error(result.errorText)
    if (method === 'Page.navigate' && !result.loaderId) return result
    await waitFor(async () => {
      try {
        const state = await command('Runtime.evaluate', { returnByValue: true,
          expression: `window.__navigationToken!==${JSON.stringify(token)}&&document.readyState==='complete'` })
        return state.result.value === true
      } catch { return false }
    }, `new document after ${method}`)
    return result
  }
}
