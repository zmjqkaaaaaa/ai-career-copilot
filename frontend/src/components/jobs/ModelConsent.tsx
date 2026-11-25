import { useEffect, useRef } from 'react'
import type { Preview } from '../../services/jobs'

export function ModelConsent({ preview, advice, busy, onConfirm, onCancel }: {
  preview: Preview; advice: boolean; busy: boolean; onConfirm: () => void; onCancel: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])

  return <div className="career-detail grid gap-2">
    <h3 ref={heading} tabIndex={-1}>核对发送内容</h3>
    <p>接收服务 · {preview.host ?? '尚未配置'}</p>
    {advice && <p>本次发送下方的岗位要求与匹配状态摘要。</p>}
    <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words" tabIndex={0} aria-label="待发送的数据">
      {typeof preview.payload.job_description === 'string' ? preview.payload.job_description : JSON.stringify(preview.payload, null, 2)}
    </pre>
    <div className="career-actions">
      <button type="button" className="button button-filled" disabled={busy || !preview.host} onClick={onConfirm}>同意发送并执行</button>
      <button type="button" className="button button-outline" disabled={busy} onClick={onCancel}>取消</button>
    </div>
  </div>
}
