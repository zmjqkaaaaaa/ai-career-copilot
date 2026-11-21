import type { Architecture, CodeFile, Evidence, Lesson } from '../../services/codeProjects'

export function EvidenceList({ evidence, github }: { evidence: Evidence[]; github: string }) {
  return <div className="grid gap-2">{evidence.map((item) =>
    <details key={item.id} className="career-detail">
      <summary>[{item.id}] {item.path} · {item.start}–{item.end}{item.symbol && ` · ${item.symbol}`}</summary>
      <a className="text-brand underline" href={`${github}/${item.path.split('/').map(encodeURIComponent).join('/')}#L${item.start}-L${item.end}`}
        target="_blank" rel="noreferrer">在 GitHub 核对</a>
      <pre className="overflow-auto p-2 text-xs">{item.code}</pre>
    </details>)}</div>
}

const basis: Record<string, string> = { observed: '代码可见', inferred: '静态推断', unknown: '证据不足', suggestion: '建议' }

export function LessonCard({ lesson, github }: { lesson: Lesson; github: string }) {
  return <article className="surface detail-panel grid gap-3">
    {lesson.question && <h3>{lesson.question}</h3>}
    <p>{lesson.overview}</p>
    {lesson.sections.map((part, i) => <div key={i} className="career-detail">
      <h4 className="font-semibold">{part.title} · {basis[part.status]}</h4>
      <p className="whitespace-pre-wrap">{part.explanation}</p>
      <EvidenceList github={github} evidence={lesson.evidence.filter((ref) => part.references.includes(ref.id))} />
    </div>)}
    {!!lesson.missing.length && <p>还需核对 · {lesson.missing.join('；')}</p>}
    {!!lesson.exercises.length && <ul>{lesson.exercises.map((item, i) => <li key={i}>{item}</li>)}</ul>}
  </article>
}

type Branch = { dirs: Map<string, Branch>; files: CodeFile[] }
const branch = (): Branch => ({ dirs: new Map(), files: [] })

function Directory({ tree, active, onSelect, depth = 0 }: {
  tree: Branch; active: number | null; onSelect: (file: number) => void; depth?: number
}) {
  return <ul className={depth ? 'ml-4 border-l border-line pl-2' : ''}>
    {Array.from(tree.dirs.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([name, child]) =>
      <li key={name}><details open={depth < 1}><summary className="cursor-pointer py-1">{name}/</summary>
        <Directory tree={child} active={active} onSelect={onSelect} depth={depth + 1} />
      </details></li>)}
    {tree.files.map((file) => <li key={file.id}>
      <button type="button" className="max-w-full break-all py-1 text-left aria-pressed:font-bold aria-pressed:text-brand"
        aria-pressed={active === file.id} onClick={() => onSelect(file.id)} title={file.path}>
        {file.path.split('/').at(-1)} <span className="text-xs text-muted">{file.loaded ? '已读取' : file.readable ? '' : '超出读取范围'}</span>
      </button>
    </li>)}
  </ul>
}

export function FileTree({ files, active, onSelect }: { files: CodeFile[]; active: number | null; onSelect: (file: number) => void }) {
  const root = branch()
  for (const file of files) {
    let current = root
    for (const part of file.path.split('/').slice(0, -1)) {
      if (!current.dirs.has(part)) current.dirs.set(part, branch())
      current = current.dirs.get(part)!
    }
    current.files.push(file)
  }
  return <Directory tree={root} active={active} onSelect={onSelect} />
}

export function ArchitectureIndex({ value, github }: { value: Architecture; github: string }) {
  function link(path: string, line: number) {
    return <a href={`${github}/${path.split('/').map(encodeURIComponent).join('/')}#L${line}`} target="_blank"
      rel="noreferrer" className="text-brand underline">{path}:{line}</a>
  }
  return <section className="surface detail-panel grid gap-3">
    <h2>技术栈与静态索引</h2>
    <p>已读 {value.files_read} 个文件，文件树收录 {value.files_indexed} 项。</p>
    <ul>{value.tech_stack.map((item) => <li key={item.name}>{item.name} · {item.category} · {link(item.path, item.line)}</li>)}</ul>
    <details className="career-detail"><summary>项目入口与模块</summary>
      <ul>{value.entries.map((item) => <li key={item.path}>{link(item.path, item.line)} · 推断 · {item.reason}</li>)}</ul>
      <ul>{value.modules.map((item) => <li key={item.path}>{item.module} · {item.path} · {item.symbols} 个符号</li>)}</ul>
    </details>
    <details className="career-detail"><summary>API 路由与数据模型（{value.routes.length + value.models.length}）</summary>
      <ul>{value.routes.map((item, i) => <li key={i}>{item.method} {item.path} · {item.name} · {link(item.file, item.line)}</li>)}
        {value.models.map((item, i) => <li key={i}>{item.name} · 模型候选 · {link(item.path, item.line)}</li>)}</ul>
      {!value.routes.length && !value.models.length && <p>当前已读文件未识别到路由或模型声明。</p>}
    </details>
    <details className="career-detail"><summary>文件导入与可能的函数调用（{value.imports.length + value.calls.length}）</summary>
      <ul>{value.imports.map((item, i) => <li key={i}>{link(item.from, item.line)} → {item.to}</li>)}
        {value.calls.map((item, i) => <li key={i}>{item.caller} → {item.name} · 推断 · {link(item.file, item.line)}</li>)}</ul>
    </details>
  </section>
}
