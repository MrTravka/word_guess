import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCampaign } from './useCampaign'
import shared from '../Account.module.css'
import styles from './Campaign.module.css'

const offset = (index: number) => Math.round(Math.sin(index * Math.PI / 4) * 65)
const trail = Array.from({ length: 20 }, (_, index) => {
  const x = 160 + offset(index)
  const y = 52 + index * 104
  return index === 0 ? `M ${x} ${y}` : `S ${x} ${y - 52}, ${x} ${y}`
}).join(' ')

export default function CampaignScreen({ userId }: { userId: number }) {
  const [chapter, setChapter] = useState<number>()
  const query = useCampaign(userId, chapter)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [chapter])
  const map = query.data

  return <section className={styles.campaign} aria-labelledby="campaign-heading">
    <div className={styles.heading}>
      <h1 id="campaign-heading" tabIndex={-1} ref={heading}>Кампания</h1>
      <Link className={shared.secondary} to="/#modes-heading">Режимы</Link>
    </div>
    <p>Шесть попыток на слово. Победа открывает следующий уровень, поражение даёт новое слово на том же уровне.</p>
    {query.isPending && <p role="status">Загружаем карту…</p>}
    {query.error && <p role="alert">{query.error.message}
      {' '}<button className={shared.secondary} onClick={() => { void query.refetch() }}>Повторить</button></p>}
    {map && <>
      <div className={styles.summary}>
        <strong>Текущий уровень: {map.current_level}</strong>
        <Link className={shared.primary} to="/play/campaign">Продолжить кампанию</Link>
        <p>Сундуков получено: {map.chests}. Сундук сохраняется за каждый десятый пройденный уровень.
          {' '}Открытие пока недоступно.</p>
      </div>
      <details className={styles.rules}><summary>Как получить звёзды</summary>
        <p>3 звезды — за 1–2 попытки без подсказок; 2 — за 3–4; 1 — за 5–6 или с подсказками.
          Любая победа открывает путь дальше. Пройденные уровни сохраняются и повторно не играются.</p>
      </details>
      <div className={styles.chapters} aria-label="Главы кампании">
        <button className={shared.secondary} disabled={!map.previous_chapter}
          onClick={() => setChapter(map.previous_chapter ?? undefined)}>Назад</button>
        <h2>Глава {map.chapter}</h2>
        <button className={shared.secondary} disabled={!map.next_chapter}
          onClick={() => setChapter(map.next_chapter ?? undefined)}>Дальше</button>
      </div>
      {map.chapter !== map.current_chapter && <button className={shared.secondary}
        onClick={() => setChapter(undefined)}>К текущей главе</button>}
      <div className={styles.map}>
        <svg className={styles.trail} viewBox="0 0 320 2080" aria-hidden="true"><path d={trail} /></svg>
        <ol className={styles.levels} start={(map.chapter - 1) * 20 + 1} aria-label={`Уровни главы ${map.chapter}`}>
          {map.levels.map((level, index) => {
            const label = `Уровень ${level.level}: ${level.status === 'completed' ? `пройден, звёзд ${level.stars}`
              : level.status === 'current' ? 'доступен' : 'закрыт'}`
            const content = <><strong>{level.level}</strong><span>{level.length} {level.length === 4 ? 'буквы' : 'букв'} · {level.status === 'completed'
              ? '★'.repeat(level.stars) : level.status === 'current' ? 'Играть' : 'Закрыт'}</span>
              {level.milestone && <small>{level.chest_id ? '✓ Сундук получен' : '◇ Сундук'}</small>}</>
            return <li key={level.level} style={{ transform: `translateX(${offset(index)}px)` }}>
              {level.status === 'current' ? <Link to="/play/campaign" className={styles.current}
                aria-label={label} aria-current="step">{content}</Link>
                : <div className={level.status === 'completed' ? styles.completed : styles.locked}
                  aria-label={label}>{content}</div>}
            </li>
          })}
        </ol>
      </div>
      <div className={styles.bottom}><Link className={shared.primary} to="/play/campaign">Продолжить кампанию</Link></div>
    </>}
  </section>
}
