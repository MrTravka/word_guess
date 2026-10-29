import { useEffect, useRef, useSyncExternalStore } from 'react'

let writes = 0
const blockers = new Set<symbol>()
const listeners = new Set<() => void>()
const notify = () => listeners.forEach((listener) => listener())
export function beginWrite() {
  writes++
  notify()
  return () => { writes--; notify() }
}
export function useUpdateGuard(blocked: boolean) {
  const owner = useRef(Symbol())
  useEffect(() => {
    const key = owner.current
    if (blocked) blockers.add(key)
    notify()
    return () => { blockers.delete(key); notify() }
  }, [blocked])
}
export function updateBlocked() { return writes > 0 || blockers.size > 0 }
export function useUpdateBlocked() {
  return useSyncExternalStore((listener) => { listeners.add(listener); return () => { listeners.delete(listener) } }, updateBlocked)
}
