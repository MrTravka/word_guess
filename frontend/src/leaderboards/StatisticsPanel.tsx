import type { Statistics } from './types'
import styles from './Leaderboards.module.css'

export default function StatisticsPanel({ statistics }: { statistics: Statistics }) {
  const max = Math.max(1, ...statistics.attempt_distribution.map((row) => row.wins))
  const items = [
    ['Завершено партий', statistics.games], ['Побед', statistics.wins], ['Поражений', statistics.losses],
    ['Процент побед', `${statistics.win_rate.toLocaleString('ru-RU')}%`],
    ['Среднее попыток', statistics.average_attempts?.toLocaleString('ru-RU') ?? '—'], ['Лучшая серия побед', statistics.best_streak],
  ]
  return <section className={styles.statistics} aria-labelledby="statistics-heading">
    <h2 id="statistics-heading" tabIndex={-1}>Ваша статистика</h2>
    <dl className={styles.metrics}>{items.map(([label, value]) => <div key={label}>
      <dt>{label}</dt><dd>{value}</dd>
    </div>)}</dl>
    <h3>За сколько попыток вы побеждали</h3>
    <ol className={styles.distribution} aria-label="Распределение попыток по победам">
      {statistics.attempt_distribution.map((row) => <li key={row.attempt} aria-label={`Попыток: ${row.attempt}. Побед: ${row.wins}.`}>
        <span aria-hidden="true">{row.attempt}</span><div className={styles.barTrack} aria-hidden="true">
          <div className={styles.bar} style={{ width: `${row.wins / max * 100}%` }} />
        </div><strong aria-hidden="true">{row.wins}</strong>
      </li>)}
    </ol>
    <p className={styles.help}>Среднее и распределение учитывают победы. Поражения включают сдачи
      ({statistics.surrendered}). Серия — победы подряд в этом режиме; активная партия в статистику не входит.</p>
  </section>
}
