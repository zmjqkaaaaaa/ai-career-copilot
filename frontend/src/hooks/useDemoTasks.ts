import { useEffect, useState } from 'react'
import { tasks } from '../data/dashboardMock'
import type { TaskId } from '../data/dashboardMock'

const storageKey = 'ai-career-copilot.demo-tasks.v1'

function readCompletedTasks(): TaskId[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(storageKey) ?? '[]')
    // Reuse the known task IDs to discard outdated or malformed stored values.
    return Array.isArray(stored)
      ? tasks.filter(({ id }) => stored.includes(id)).map(({ id }) => id)
      : []
  } catch {
    return []
  }
}

export function useDemoTasks() {
  const [completed, setCompleted] = useState(readCompletedTasks)

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(completed))
    } catch {
      // Task toggles remain available when browser storage is blocked.
    }
  }, [completed])

  function toggle(id: TaskId) {
    setCompleted((current) => current.includes(id)
      ? current.filter((taskId) => taskId !== id)
      : [...current, id])
  }

  return { completed, toggle }
}
