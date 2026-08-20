import { useState, useEffect } from 'react'
import { Layout, type View } from './components/Layout'
import { Overview } from './views/Overview'
import { Explore } from './views/Explore'
import { Sentiment } from './views/Sentiment'
import { Entities } from './views/Entities'
import { Graph } from './views/Graph'
import { Stories } from './views/Stories'
import { Sources } from './views/Sources'
import { Alerts } from './views/Alerts'

export default function App() {
  const [view, setView] = useState<View>('overview')
  const [search, setSearch] = useState('')
  const [online, setOnline] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.ok ? setOnline(true) : setOnline(false))
      .catch(() => setOnline(false))
  }, [])

  const handleSearch = (s: string) => {
    setSearch(s)
    if (s.trim()) setView('explore')
  }

  return (
    <Layout view={view} onNav={setView} search={search} onSearch={handleSearch} online={online}>
      {view === 'overview' && <Overview search={search} />}
      {view === 'explore' && <Explore initialQuery={search} />}
      {view === 'sentiment' && <Sentiment />}
      {view === 'entities' && <Entities />}
      {view === 'graph' && <Graph />}
      {view === 'stories' && <Stories />}
      {view === 'alerts' && <Alerts />}
      {view === 'sources' && <Sources />}
    </Layout>
  )
}
