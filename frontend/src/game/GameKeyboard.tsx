import { marks, type Game } from './types'
import styles from './Game.module.css'

type Props = { game: Game; disabled: boolean; press: (key: string) => void }

export default function GameKeyboard({ game, disabled, press }: Props) {
  return <div className={styles.keyboard} role="group" aria-label="Экранная клавиатура">
    {['йцукенгшщзхъ', 'фывапролджэ', 'ячсмитьбю'].map((row, index) => <div className={styles.keys} key={row}>
      {index === 2 && <button className={styles.wideKey} disabled={disabled} aria-label="Отправить слово"
        onPointerDown={(event) => event.preventDefault()} onClick={() => press('Enter')}>Ввод</button>}
      {[...row].map((letter) => {
        const mark = game.keyboard[letter]
        return <button key={letter} data-mark={mark} disabled={disabled}
          aria-label={`${letter.toUpperCase()}${mark ? `: ${marks[mark].label}` : ''}`}
          onPointerDown={(event) => event.preventDefault()} onClick={() => press(letter)}>
          {letter.toUpperCase()}{mark && <small aria-hidden="true">{marks[mark].symbol}</small>}
        </button>
      })}
      {index === 2 && <button className={styles.wideKey} disabled={disabled} aria-label="Удалить букву"
        onPointerDown={(event) => event.preventDefault()} onClick={() => press('Backspace')}>⌫</button>}
    </div>)}
  </div>
}
