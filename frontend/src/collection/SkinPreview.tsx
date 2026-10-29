import styles from './skins.module.css'

export default function SkinPreview({ skinId }: { skinId: string }) {
  return <div className={`${styles.surface} ${styles.preview}`} data-skin={skinId}
    aria-label="Предпросмотр: на месте, в другом месте, без совпадения">
    {(['correct', 'present', 'absent'] as const).map((mark, index) => <span key={mark}
      className={styles.cell} data-word-cell="" data-mark={mark} aria-hidden="true">
      {'ЛЁН'[index]}<small>{['●', '↔', '×'][index]}</small>
    </span>)}
  </div>
}
