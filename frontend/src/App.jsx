import { useEffect, useMemo, useState } from 'react'

const ACCEPT = '.cpp,.c,.py,.java'
const TOKEN_KEY = 'print_portal_token'
const USER_KEY = 'print_portal_user'

function api(path, options = {}, token) {
  const headers = { ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`

  return fetch(path, { ...options, headers }).then(async (res) => {
    const text = await res.text()
    let data = {}
    try {
      data = text ? JSON.parse(text) : {}
    } catch {
      data = { message: text }
    }
    if (!res.ok) {
      throw new Error(data.description || data.message || `HTTP ${res.status}`)
    }
    return data
  })
}

export default function App() {
  const [username, setUsername] = useState(localStorage.getItem(USER_KEY) || '')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY) || '')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [jobs, setJobs] = useState([])

  const loggedIn = useMemo(() => Boolean(token), [token])

  async function refreshJobs(authToken = token) {
    if (!authToken) return
    const data = await api('/api/jobs', {}, authToken)
    setJobs(data.jobs || [])
  }

  useEffect(() => {
    if (!token) return
    api('/api/auth/me', {}, token)
      .then((data) => {
        if (data.username) {
          setUsername(data.username)
          localStorage.setItem(USER_KEY, data.username)
          refreshJobs(token).catch(() => {})
        }
      })
      .catch(() => {
        logout()
      })
  }, [])

  async function login(e) {
    e.preventDefault()
    setLoading(true)
    setMessage('')
    try {
      const data = await api('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })
      setToken(data.access_token)
      localStorage.setItem(TOKEN_KEY, data.access_token)
      localStorage.setItem(USER_KEY, data.username)
      setPassword('')
      setMessage(`Logged in as ${data.username}`)
      await refreshJobs(data.access_token)
    } catch (err) {
      setMessage(err.message)
    } finally {
      setLoading(false)
    }
  }

  function logout() {
    setToken('')
    setJobs([])
    setPassword('')
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setMessage('Logged out')
  }

  async function uploadFile(e) {
    e.preventDefault()
    if (!file) {
      setMessage('Select a file first.')
      return
    }

    setLoading(true)
    setMessage('')
    try {
      const formData = new FormData()
      formData.append('file', file)

      const data = await api(
        '/api/upload',
        {
          method: 'POST',
          body: formData
        },
        token
      )
      setMessage(`Queued job #${data.job_id} (${data.filename})`)
      setFile(null)
      const input = document.getElementById('file-input')
      if (input) input.value = ''
      await refreshJobs()
    } catch (err) {
      setMessage(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <div className="grain" />
      <main className="panel">
        <header>
          <p className="eyebrow">PRINT PORTAL</p>
          <h1>Ship code to paper.</h1>
          <p className="sub">Upload source files and queue a print job to the local printer bridge.</p>
        </header>

        {!loggedIn ? (
          <form className="stack" onSubmit={login}>
            <label>
              Username
              <input value={username} onChange={(e) => setUsername(e.target.value)} required />
            </label>
            <label>
              Password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <button disabled={loading}>{loading ? 'Signing in...' : 'Login'}</button>
          </form>
        ) : (
          <>
            <div className="user-row">
              <span>Signed in as <strong>{username}</strong></span>
              <button className="ghost" onClick={logout} type="button">Logout</button>
            </div>

            <form className="stack" onSubmit={uploadFile}>
              <label>
                Source file
                <input
                  id="file-input"
                  type="file"
                  accept={ACCEPT}
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  required
                />
              </label>
              <button disabled={loading}>{loading ? 'Uploading...' : 'Upload & Queue Print'}</button>
            </form>

            <section className="jobs">
              <div className="jobs-head">
                <h2>Your recent jobs</h2>
                <button className="ghost" type="button" onClick={() => refreshJobs()}>
                  Refresh
                </button>
              </div>
              {jobs.length === 0 ? (
                <p className="muted">No jobs yet.</p>
              ) : (
                <ul>
                  {jobs.map((job) => (
                    <li key={job.id}>
                      <span>#{job.id} {job.original_name}</span>
                      <b className={`status s-${job.status}`}>{job.status}</b>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        {message ? <p className="message">{message}</p> : null}
      </main>
    </div>
  )
}
