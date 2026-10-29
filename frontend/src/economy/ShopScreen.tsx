import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api'
import { operationId } from '../operationId'
import { useEconomy } from './useEconomy'
import type { CatalogItem, Economy, HintKind } from './types'
import shared from '../Account.module.css'
import styles from './Shop.module.css'
import { useUpdateGuard } from '../pwa/activity'

export default function ShopScreen({ userId }: { userId: number }) {
  const client = useQueryClient()
  const wallet = useEconomy(userId)
  const catalog = useQuery({ queryKey: ['shop', userId], queryFn: () => api<{ catalog: CatalogItem[] }>('/shop'), retry: false })
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<{ item: HintKind; operation_id: string } | null>(null)
  const [message, setMessage] = useState('')
  const lock = useRef(false)
  useUpdateGuard(busy || pending !== null)

  async function purchase(item: HintKind) {
    if (lock.current) return
    const body = pending ?? { item, operation_id: operationId() }
    lock.current = true
    setBusy(true)
    setMessage('')
    await client.cancelQueries({ queryKey: ['inventory', userId] })
    try {
      const result = await api<{ economy: Economy; purchase: { price: number } }>('/shop/purchases', 'POST', body)
      client.setQueryData(['inventory', userId], result.economy)
      setPending(null)
      setMessage(`Покупка добавлена в инвентарь. Списано ${result.purchase.price} монет.`)
    } catch (cause) {
      const error = cause as ApiError
      setMessage(error.message)
      setPending(error.status === 0 || error.status >= 500 ? body : null)
      if (error.status === 409) void wallet.refetch()
    } finally { lock.current = false; setBusy(false) }
  }

  return <section className={styles.shop} aria-labelledby="shop-heading">
    <div className={styles.heading}><h1 id="shop-heading">Магазин подсказок</h1><Link to="/" className={shared.secondary}>На главную</Link></div>
    <p>Покупайте за игровые монеты и используйте в любой своей партии. Применение подсказки уменьшает очки за победу; монеты за победу сохраняются.</p>
    <p className={styles.balance}>Баланс: <strong>{wallet.data?.coins ?? '…'}</strong> монет</p>
    <p><Link className={shared.secondary} to="/collection">Коллекция и сундуки</Link></p>
    {(catalog.error || wallet.error) && <p role="alert">{(catalog.error || wallet.error)?.message}
      {' '}<button className={shared.secondary} onClick={() => { void catalog.refetch(); void wallet.refetch() }}>Повторить</button></p>}
    <div className={styles.items}>
      {catalog.data?.catalog.map((item) => <article className={styles.item} key={item.id}>
        <h2>{item.title}</h2><p>{item.description}</p>
        <p>В инвентаре: <strong>{wallet.data?.inventory[item.id] ?? '…'}</strong></p>
        <button className={shared.primary} disabled={busy || Boolean(pending) || !wallet.data || wallet.data.coins < item.price}
          onClick={() => { void purchase(item.id) }}>Купить за {item.price}</button>
      </article>)}
    </div>
    <p role="status" aria-live="polite">{busy ? 'Покупаем…' : message}</p>
    {pending && <button className={shared.secondary} disabled={busy} onClick={() => { void purchase(pending.item) }}>Повторить покупку</button>}
    <p className={styles.help}>Покупка добавляет один предмет. Примените его отдельно на экране партии; перед применением можно отменить выбор.</p>
  </section>
}
