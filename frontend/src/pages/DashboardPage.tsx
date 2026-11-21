import { CoreModules } from '../components/dashboard/CoreModules'
import { GrowthPath } from '../components/dashboard/GrowthPath'
import { Overview } from '../components/dashboard/Overview'
import { RecentTasks } from '../components/dashboard/RecentTasks'
import { SkillProfile } from '../components/dashboard/SkillProfile'
import { Welcome } from '../components/dashboard/Welcome'

export function DashboardPage() {
  return (
    <div className="dashboard">
      <Welcome />
      <Overview />
      <CoreModules />
      <div className="dashboard-details">
        <SkillProfile />
        <RecentTasks />
      </div>
      <GrowthPath />
    </div>
  )
}
