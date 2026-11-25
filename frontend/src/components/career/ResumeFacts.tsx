import { useState } from 'react'
import { factGroups } from '../../services/career'
import type { Block, Fact, Facts } from '../../services/career'

const groups = Object.keys(factGroups) as (keyof Facts)[]

function unquotedBlocks(blocks: Block[], facts: Facts) {
  const quotes = new Map<number, Set<string>>()
  for (const group of groups) {
    for (const fact of facts[group]) {
      if (!fact.source || fact.original !== fact.source.quote) continue
      const { block_number, quote } = fact.source
      const existing = quotes.get(block_number) ?? new Set<string>()
      existing.add(quote)
      quotes.set(block_number, existing)
    }
  }
  return blocks.filter((block) => {
    const covered = new Uint8Array(block.text.length)
    for (const quote of quotes.get(block.number) ?? []) {
      const start = block.text.indexOf(quote)
      if (start >= 0) covered.fill(1, start, start + quote.length)
    }
    const rest = block.text.replaceAll('[已脱敏]', '     ')
    return /[\p{L}\p{N}]/u.test(rest.split('').filter((_, index) => !covered[index]).join(''))
  })
}

export function ResumeFacts({ facts, modelBlocks, confirmed, disabled, onSave }: {
  facts: Facts; modelBlocks: Block[]; confirmed: boolean; disabled: boolean; onSave?: (facts: Facts) => void
}) {
  const [draft, setDraft] = useState(facts)
  const [sourceGroup, setSourceGroup] = useState<keyof Facts | ''>('')
  const missing = unquotedBlocks(modelBlocks, draft)

  function update(group: keyof Facts, index: number, values: Partial<Fact>) {
    setDraft((current) => ({ ...current, [group]: current[group].map((item, position) => position === index ? { ...item, ...values } : item) }))
  }

  return (
    <form className="account-form" onSubmit={(event) => {
      event.preventDefault()
      onSave?.(draft)
    }}>
      {onSave && <p className="panel-description">请重点核对项目与实习中的个人行动、交付物和验证结果。手动更正不改变原始文件。</p>}
      <fieldset className="grid gap-3" disabled={disabled || !onSave}>
        {onSave && modelBlocks.length > 0 && <details className="career-detail">
          <summary>核对简历原文（{missing.length} 个段落含未引用文字）</summary>
          <p className="panel-description">这里只检查哪些脱敏文字被逐字引用。标题和重复说明也可能出现在此处。发现遗漏时，可以补入相应分类。</p>
          <label>补充到<select value={sourceGroup} onChange={(event) => setSourceGroup(event.target.value as keyof Facts | '')}>
            <option value="">按原文章节</option>
            {groups.map((group) => <option key={group} value={group}>{factGroups[group]}</option>)}
          </select></label>
          {missing.map((block) => {
            const target = sourceGroup || block.section || 'other_experiences'
            const groupFull = draft[target].length >= (target === 'skills' ? 35 : 15)
            return <div key={block.number} className="experience-entry">
            <small>段落 {block.number} · {block.location} · 补入{factGroups[target]}</small>
            <blockquote className="whitespace-pre-wrap">{block.text}</blockquote>
            {groupFull && <p className="panel-description">该分类已达到条目上限，请先删除重复条目。</p>}
            {block.text.trim().split(/\n/).map((line) => line.trim()).filter((line, index, lines) =>
              line.length > 0 && line.length <= 1200 && /[\p{L}\p{N}]/u.test(line.replaceAll('[已脱敏]', '')) && lines.indexOf(line) === index
            ).map((line) => <button type="button" key={line} className="button button-outline"
              disabled={groupFull || draft[target].some((fact) => fact.source?.block_number === block.number && fact.original === line)}
              onClick={() => setDraft((previous) => ({ ...previous, [target]: [
                ...previous[target], { original: line, normalized: null, source: { block_number: block.number, quote: line }, status: 'user_confirmed' },
              ] }))}>补入：{line.length > 40 ? line.slice(0, 40) + '…' : line}</button>)}
          </div>
          })}
        </details>}
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
                {onSave && <button type="button" className="button button-outline" onClick={() => setDraft((current) => ({
                  ...current, [group]: current[group].filter((_, position) => position !== index),
                }))}>移除此项</button>}
              </div>
            ))}
            {onSave && <button type="button" className="button button-outline" disabled={draft[group].length >= (group === 'skills' ? 35 : 15)}
              onClick={() => setDraft((current) => ({ ...current, [group]: [
                ...current[group], { original: '', normalized: null, source: null, status: 'user_confirmed' },
              ] }))}>添加{factGroups[group]}</button>}
          </details>
        ))}
      </fieldset>
      {onSave && <button className="button button-filled" disabled={disabled}>{confirmed ? '保存修正' : '确认结构化简历'}</button>}
    </form>
  )
}
