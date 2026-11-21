import { useState } from 'react'
import { factGroups } from '../../services/career'
import type { Fact, Facts } from '../../services/career'

const groups = Object.keys(factGroups) as (keyof Facts)[]

export function ResumeFacts({ facts, confirmed, disabled, onSave }: {
  facts: Facts; confirmed: boolean; disabled: boolean; onSave: (facts: Facts) => void
}) {
  const [draft, setDraft] = useState(facts)

  function update(group: keyof Facts, index: number, values: Partial<Fact>) {
    setDraft((current) => ({ ...current, [group]: current[group].map((item, position) => position === index ? { ...item, ...values } : item) }))
  }

  return (
    <form className="account-form" onSubmit={(event) => {
      event.preventDefault()
      onSave(draft)
    }}>
      <p className="panel-description">核对模型提取的条目后再确认。手动更正不改变原始文件。</p>
      <fieldset className="grid gap-3" disabled={disabled}>
        {groups.map((group) => (
          <details className="career-detail" key={group} open={group === 'education' || undefined}>
            <summary>{factGroups[group]}（{draft[group].length}）</summary>
            {draft[group].map((fact, index) => (
              <div className="experience-entry" key={index}>
                <label>原始内容<textarea rows={2} value={fact.original} maxLength={1200} required
                  onChange={(event) => update(group, index, { original: event.target.value, source: null })} /></label>
                <label>整理后内容<input value={fact.normalized ?? ''} maxLength={400}
                  onChange={(event) => update(group, index, { normalized: event.target.value || null })} /></label>
                {fact.source && <p className="panel-description">段落 {fact.source.block_number} · {fact.source.quote}</p>}
                {fact.status === 'uncertain' && <p className="panel-description">待核对</p>}
                <button type="button" className="button button-outline" onClick={() => setDraft((current) => ({
                  ...current, [group]: current[group].filter((_, position) => position !== index),
                }))}>移除此项</button>
              </div>
            ))}
            <button type="button" className="button button-outline" disabled={draft[group].length >= (group === 'skills' ? 35 : 15)}
              onClick={() => setDraft((current) => ({ ...current, [group]: [
                ...current[group], { original: '', normalized: null, source: null, status: 'user_confirmed' },
              ] }))}>添加{factGroups[group]}</button>
          </details>
        ))}
      </fieldset>
      <button className="button button-filled" disabled={disabled}>{confirmed ? '保存修正' : '确认结构化简历'}</button>
    </form>
  )
}
