import type { ReactNode } from 'react'

export function Feedback({ kind, children, retry }: {
  kind: 'loading' | 'error' | 'empty' | 'success'
  children: ReactNode
  retry?: () => void
}) {
  const message = <p className={kind === 'error' ? 'form-error' : kind === 'success' ? 'form-success' : 'panel-description'}
    role={kind === 'error' ? 'alert' : kind === 'empty' ? undefined : 'status'}>{children}</p>
  if (!retry) return message
  return <div>
    {message}
    <button type="button" className="button button-outline mt-2" onClick={retry}>重试</button>
  </div>
}
