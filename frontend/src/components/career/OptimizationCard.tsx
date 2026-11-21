import { useState } from 'react'
import type { Optimization } from '../../services/career'

export function OptimizationCard({ record, disabled, onConfirm }: {
  record: Optimization; disabled: boolean; onConfirm: (text: string) => void
}) {
  const [text, setText] = useState(record.confirmed_text ?? record.optimized_content)
  return <article className="surface detail-panel">
    <div className="section-heading">
      <h3>{record.section}优化 · 段落 {record.block_number}</h3>
      <span className="badge">{record.confirmed_text ? '已确认' : record.needs_evidence ? '待补证' : '待确认'}</span>
    </div>
    <div className="career-grid">
      <div><strong>原始描述</strong><blockquote>{record.original_content}</blockquote></div>
      <div><strong>AI 修改建议</strong><blockquote>{record.optimized_content}</blockquote></div>
    </div>
    <p className="panel-description">{record.optimization_reason}</p>
    <p className="panel-description">可能的面试追问 · {record.interview_question}</p>
    {record.confirmed_text ? <div><strong>已保存版本</strong><blockquote>{record.confirmed_text}</blockquote></div> : (
      <form className="account-form" onSubmit={(event) => { event.preventDefault(); if (text.trim()) onConfirm(text.trim()) }}>
        <label>修改后内容<textarea rows={3} maxLength={1200} required value={text} onChange={(event) => setText(event.target.value)} /></label>
        <button className="button button-filled" disabled={disabled || !text.trim()}>确认并保存文本版本</button>
      </form>
    )}
  </article>
}
