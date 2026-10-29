import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import styles from './App.module.css'
import shared from './Account.module.css'

const modes = [
  { title: '4 буквы', description: 'Короткое слово. Большое начало.', number: '04', path: '/play/4' },
  { title: '5 букв', description: 'Знакомая длина, новые открытия.', number: '05', path: '/play/5' },
  { title: '6 букв', description: 'Чуть больше места для догадки.', number: '06', path: '/play/6' },
  { title: 'Кампания', description: 'Слово за словом, уровень за уровнем.', number: '∞', path: '/campaign' },
]

export default function ModeSelection() {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])

  return <section className={styles.modes} aria-labelledby="modes-heading">
    <div className={styles.sectionTitle}>
      <h1 id="modes-heading" ref={heading} tabIndex={-1}>Выберите режим</h1>
      <Link className={shared.secondary} to="/">На главную</Link>
    </div>
    <div className={styles.cards}>
      {modes.map((mode) => <article className={styles.card} key={mode.title}>
        <span className={styles.modeNumber} aria-hidden="true">{mode.number}</span>
        <h2>{mode.title}</h2><p>{mode.description}</p>
        <Link className={shared.primary} to={mode.path}
          aria-label={`Открыть режим «${mode.title}»`}>Открыть</Link>
      </article>)}
    </div>
  </section>
}
