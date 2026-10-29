import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import type { Chest } from './types'
import { rarity } from './types'
import shared from '../Account.module.css'
import styles from './ChestReel.module.css'

export default function ChestReel({ opening, finish }: { opening: NonNullable<Chest['opening']>; finish: () => void }) {
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)')
    const timer = window.setTimeout(finish, media.matches ? 120 : 4500)
    const changed = () => { if (media.matches) finish() }
    media.addEventListener('change', changed)
    return () => { window.clearTimeout(timer); media.removeEventListener('change', changed) }
  }, [finish])
  return <div className={styles.reveal}>
    <p role="status">Открываем сундук…</p>
    <div className={styles.viewport} aria-hidden="true">
      <span className={styles.pointer} />
      <div className={styles.track} style={{ '--stop': `${opening.result.winner_index * 144 + 66}px` } as CSSProperties}>
        {opening.result.reel.map((prize, index) => <div className={styles.card} data-rarity={prize.rarity} key={index}>
          <span>{prize.kind === 'coins' ? '◉' : '◇'}</span><strong>{prize.title}</strong><small>{rarity[prize.rarity]}</small>
        </div>)}
      </div>
    </div>
    <button className={shared.primary} onClick={finish}>Пропустить</button>
    <p className={styles.note}>Награда уже получена. Пропуск и закрытие страницы сохранят её.</p>
  </div>
}
