import { useEffect, useState } from 'react'
import { Feedback } from '../components/common/Feedback'
import { CoreModules } from '../components/dashboard/CoreModules'
import { GrowthPath } from '../components/dashboard/GrowthPath'
import { OverviewPanel, ProgressOverview } from '../components/dashboard/ProgressOverview'
import { Welcome } from '../components/dashboard/Welcome'
import { useAuth } from '../hooks/AuthProvider'
import { errorMessage } from '../services/api'
import { loadDashboard, type Dashboard } from '../services/dashboard'

function SignedInDashboard() {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ data: Dashboard } | { error: string } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    loadDashboard(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setResult({ data }) })
      .catch((error: unknown) => { if (!controller.signal.aborted) setResult({ error: errorMessage(error) }) })
    return () => controller.abort()
  }, [attempt])

  const data = result && 'data' in result ? result.data : undefined
  return <>
    <Welcome data={data} failed={Boolean(result && 'error' in result)} />
    {data ? <ProgressOverview data={data} /> : <OverviewPanel title="个人求职进展">
      {result && 'error' in result ? <Feedback kind="error" retry={() => {
        setResult(null)
        setAttempt((value) => value + 1)
      }}>{result.error}</Feedback> : <Feedback kind="loading">正在读取你的求职进展…</Feedback>}
    </OverviewPanel>}
  </>
}

export function DashboardPage() {
  const { account, checking } = useAuth()
  return (
    <div className="dashboard">
      {checking ? <OverviewPanel title="求职驾驶舱"><Feedback kind="loading">正在确认登录状态…</Feedback></OverviewPanel>
        : account ? <SignedInDashboard key={account.id} /> : <Welcome />}
      <CoreModules />
      {!account && !checking && <GrowthPath />}
    </div>
  )
}
