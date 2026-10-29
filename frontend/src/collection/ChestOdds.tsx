import { rarity, type Odds } from './types'
import styles from './Collection.module.css'

export default function ChestOdds({ odds }: { odds: Odds }) {
  return <details className={styles.odds}><summary>Шансы наград</summary>
    <table><thead><tr><th>Награда</th><th>Редкость</th><th>Шанс</th></tr></thead>
      <tbody>{odds.prizes.map((prize, index) => <tr key={index}><td>{prize.title}</td>
        <td>{rarity[prize.rarity]}</td><td>{prize.percent}%</td></tr>)}</tbody></table>
    <p>Каждый из {odds.skin_count} скинов равновероятен внутри категории. Если скин уже есть,
      вы получите {odds.duplicate_coins} монет. Шансы постоянны, гарантированного повышения нет.</p>
    <p>Карточки в ленте служат оформлением. Их частота не отражает шансы наград.</p>
  </details>
}
