import { useState, useEffect, useRef } from 'react'
import './App.css'

// In dev the questionnaire runs on Vite (:3000) while the main app is served by FastAPI.
// Anonymous user ID shared with the main app through localStorage.
function getOrCreateUserId() {
  const fresh = () => 'user_' + Date.now() + '_' + Math.random().toString(36).slice(2, 11)
  try {
    let id = localStorage.getItem('news_ai_user_id')
    if (!id) {
      id = fresh()
      localStorage.setItem('news_ai_user_id', id)
    }
    return id
  } catch {
    return fresh() // storage unavailable (private mode): answers are saved for this visit only
  }
}

const MAIN_APP_URL = import.meta.env.VITE_MAIN_APP_URL ?? (import.meta.env.DEV ? 'http://localhost:8000/' : '/')

// Question data
const questions = [
  {
    id: 1,
    type: 'multi',
    field: 'categories',
    emoji: '📰',
    title: 'What topics catch your eye?',
    subtitle: 'Select all the news categories you\'re interested in',
    options: [
      { value: 'Technology', icon: '💻', label: 'Technology' },
      { value: 'Business', icon: '📈', label: 'Business' },
      { value: 'Politics', icon: '🏛️', label: 'Politics' },
      { value: 'Sports', icon: '⚽', label: 'Sports' },
      { value: 'Entertainment', icon: '🎬', label: 'Entertainment' },
      { value: 'Science', icon: '🔬', label: 'Science' },
      { value: 'Health', icon: '🏥', label: 'Health' },
      { value: 'World', icon: '🌍', label: 'World News' },
      { value: 'Lifestyle', icon: '✨', label: 'Lifestyle' },
      { value: 'Finance', icon: '💰', label: 'Finance' },
    ]
  },
  {
    id: 2,
    type: 'single',
    field: 'reading_depth',
    emoji: '📖',
    title: 'How deep do you dive?',
    subtitle: 'Your preferred reading style for news',
    options: [
      { value: 'headlines', icon: '⚡', label: 'Just Headlines', desc: 'Quick glance at top stories' },
      { value: 'quick', icon: '📝', label: 'Quick Reads', desc: '2-3 minute summaries' },
      { value: 'in_depth', icon: '🔍', label: 'In-Depth Analysis', desc: 'Long-form, detailed articles' },
      { value: 'mixed', icon: '🎯', label: 'Mix of Everything', desc: 'Variety based on topic' },
    ]
  },
  {
    id: 3,
    type: 'single',
    field: 'daily_time',
    emoji: '⏰',
    title: 'Time for news each day?',
    subtitle: 'How much time do you typically spend on news?',
    options: [
      { value: 'less_10', icon: '🏃', label: 'Less than 10 minutes', desc: 'Quick updates on the go' },
      { value: '10_30', icon: '☕', label: '10-30 minutes', desc: 'Morning coffee browsing' },
      { value: '30_60', icon: '📱', label: '30-60 minutes', desc: 'Dedicated reading time' },
      { value: 'more_60', icon: '🧠', label: 'More than an hour', desc: 'News enthusiast mode' },
    ]
  },
  {
    id: 4,
    type: 'multi',
    field: 'content_formats',
    emoji: '🎨',
    title: 'How do you like your news?',
    subtitle: 'Select your preferred content formats',
    options: [
      { value: 'text', icon: '📝', label: 'Text Articles' },
      { value: 'video', icon: '🎬', label: 'Video Summaries' },
      { value: 'audio', icon: '🎧', label: 'Audio / Podcasts' },
      { value: 'infographics', icon: '📊', label: 'Infographics' },
    ]
  },
  {
    id: 5,
    type: 'single',
    field: 'primary_reason',
    emoji: '🎯',
    title: 'Why do you stay informed?',
    subtitle: 'Your primary reason for consuming news',
    options: [
      { value: 'professional', icon: '💼', label: 'Professional Needs', desc: 'Work & industry updates' },
      { value: 'personal', icon: '🌟', label: 'Personal Interest', desc: 'Curiosity & staying aware' },
      { value: 'investment', icon: '📈', label: 'Investment Decisions', desc: 'Market & financial news' },
      { value: 'social', icon: '💬', label: 'Social Conversations', desc: 'Stay relevant in discussions' },
      { value: 'academic', icon: '🎓', label: 'Academic / Research', desc: 'Learning & research purposes' },
    ]
  },
  {
    id: 6,
    type: 'single-grid',
    field: 'industry',
    emoji: '🏢',
    title: "What's your industry?",
    subtitle: "We'll tailor news to your professional world",
    options: [
      { value: 'Technology', icon: '💻', label: 'Technology' },
      { value: 'Finance', icon: '🏦', label: 'Finance' },
      { value: 'Healthcare', icon: '🏥', label: 'Healthcare' },
      { value: 'Education', icon: '🎓', label: 'Education' },
      { value: 'Media', icon: '📺', label: 'Media' },
      { value: 'Retail', icon: '🛍️', label: 'Retail' },
      { value: 'Manufacturing', icon: '🏭', label: 'Manufacturing' },
      { value: 'Government', icon: '🏛️', label: 'Government' },
      { value: 'Startup', icon: '🚀', label: 'Startup' },
      { value: 'Other', icon: '🌐', label: 'Other' },
    ]
  },
  {
    id: 7,
    type: 'multi',
    field: 'regions',
    emoji: '🌍',
    title: 'Which regions interest you?',
    subtitle: 'Select all regions you want news from',
    options: [
      { value: 'Local', icon: '📍', label: 'Local News' },
      { value: 'National', icon: '🏠', label: 'National' },
      { value: 'International', icon: '🌐', label: 'International' },
      { value: 'Asia', icon: '🌏', label: 'Asia' },
      { value: 'Europe', icon: '🇪🇺', label: 'Europe' },
      { value: 'Americas', icon: '🌎', label: 'Americas' },
    ]
  },
  {
    id: 8,
    type: 'single',
    field: 'ai_summary_preference',
    emoji: '🤖',
    title: 'How do you feel about AI summaries?',
    subtitle: 'Your preference for AI-generated content',
    options: [
      { value: 'love_it', icon: '❤️', label: 'Love them!', desc: 'They save me so much time' },
      { value: 'useful_verify', icon: '🔍', label: 'Useful but I verify', desc: 'I check original sources too' },
      { value: 'prefer_human', icon: '👤', label: 'Prefer human-written', desc: 'Give me the real articles' },
      { value: 'open_to_try', icon: '🧪', label: 'Open to trying', desc: "Let's see how it goes!" },
    ]
  },
  {
    id: 9,
    type: 'sliders',
    field: 'importance',
    emoji: '⭐',
    title: 'What matters most to you?',
    subtitle: 'Rate the importance of each quality (1-5)',
    sliders: [
      { key: 'importance_timely', icon: '⚡', label: 'Timeliness', desc: 'Breaking news & real-time updates' },
      { key: 'importance_accurate', icon: '✅', label: 'Accuracy', desc: 'Fact-checked & verified content' },
      { key: 'importance_engaging', icon: '✨', label: 'Engagement', desc: 'Well-written & engaging stories' },
    ]
  }
]

function Logo() {
  return (
    <svg aria-hidden="true" width="28" height="28" viewBox="0 0 32 32" fill="none">
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366f1" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-gradient)" />
      <path d="M8 10h16M8 16h12M8 22h8" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <circle cx="24" cy="22" r="4" fill="white" opacity="0.9" />
    </svg>
  )
}

function Check() {
  return (
    <span className="option-check" aria-hidden="true">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 6 9 17l-5-5" />
      </svg>
    </span>
  )
}

function TopBar() {
  return (
    <header className="topbar">
      <a className="brand" href={MAIN_APP_URL}>
        <Logo />
        <span>Live AI News</span>
      </a>
      <a className="skip-link" href={MAIN_APP_URL}>Skip for now</a>
    </header>
  )
}

function App() {
  const [currentQuestion, setCurrentQuestion] = useState(0)
  const [responses, setResponses] = useState({
    categories: [],
    reading_depth: null,
    daily_time: null,
    content_formats: [],
    primary_reason: null,
    industry: null,
    regions: [],
    ai_summary_preference: null,
    importance_timely: 3,
    importance_accurate: 3,
    importance_engaging: 3
  })
  const [userId] = useState(getOrCreateUserId)
  const [isComplete, setIsComplete] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [direction, setDirection] = useState('next')
  const [error, setError] = useState(null)
  const headingRef = useRef(null)
  const hasInteracted = useRef(false)

  useEffect(() => {
    // Skip the questionnaire if this user already completed it
    fetch(`/api/onboarding/check/${encodeURIComponent(userId)}`)
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        if (data?.completed) window.location.href = MAIN_APP_URL
      })
      .catch(() => { /* backend unreachable: let the user fill the form anyway */ })
  }, [userId])

  useEffect(() => {
    // Move focus to the new question so keyboard and screen reader users hear it.
    if (hasInteracted.current) headingRef.current?.focus()
  }, [currentQuestion, isComplete])

  const handleMultiSelect = (field, value) => {
    setResponses(prev => {
      const current = prev[field] || []
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter(v => v !== value) }
      }
      return { ...prev, [field]: [...current, value] }
    })
  }

  const handleSingleSelect = (field, value, autoAdvance = true) => {
    setResponses(prev => ({ ...prev, [field]: value }))
    if (autoAdvance && currentQuestion < questions.length - 1) {
      // Advance only if the user hasn't already moved on (guards against double clicks).
      const from = currentQuestion
      setTimeout(() => {
        hasInteracted.current = true
        setDirection('next')
        setCurrentQuestion(prev => (prev === from ? prev + 1 : prev))
      }, 300)
    }
  }

  const handleSlider = (key, value) => {
    setResponses(prev => ({ ...prev, [key]: parseInt(value, 10) }))
  }

  const goNext = () => {
    hasInteracted.current = true
    setError(null)
    setDirection('next')
    setCurrentQuestion(prev => Math.min(prev + 1, questions.length - 1))
  }

  const goBack = () => {
    hasInteracted.current = true
    setError(null)
    setDirection('back')
    setCurrentQuestion(prev => Math.max(prev - 1, 0))
  }

  const isCurrentValid = () => {
    const q = questions[currentQuestion]
    if (q.type === 'sliders') return true
    const val = responses[q.field]
    if (Array.isArray(val)) return val.length > 0
    return val !== null
  }

  const submit = async () => {
    if (!isCurrentValid() || isLoading) return
    setIsLoading(true)
    setError(null)

    try {
      const res = await fetch('/api/onboarding', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, ...responses })
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.success) {
        hasInteracted.current = true
        setIsComplete(true)
      } else {
        setError(typeof data.detail === 'string' ? data.detail : 'Could not save your answers. Please try again.')
      }
    } catch {
      setError('Could not reach the server. Check your connection and try again.')
    }
    setIsLoading(false)
  }

  if (isComplete) {
    return (
      <div className="app">
        <TopBar />
        <main className="success-screen" role="status">
          <div className="success-icon" aria-hidden="true">🎉</div>
          <h1 ref={headingRef} tabIndex={-1}>You're all set!</h1>
          <p>Your feed will now favour the topics you picked. It keeps adapting as you read and chat.</p>
          <a className="btn btn-primary" href={MAIN_APP_URL}>
            Go to my feed
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </a>
        </main>
      </div>
    )
  }

  const q = questions[currentQuestion]
  const progress = ((currentQuestion + 1) / questions.length) * 100
  const isLast = currentQuestion === questions.length - 1
  const valid = isCurrentValid()
  const selectedCount = Array.isArray(responses[q.field]) ? responses[q.field].length : 0

  return (
    <div className="app">
      <TopBar />

      <main className="onboarding-container">
        <div className="progress-container">
          <p className="progress-text">
            <span>Question {currentQuestion + 1} of {questions.length}</span>
            <span>{Math.round(progress)}%</span>
          </p>
          <div
            className="progress-bar"
            role="progressbar"
            aria-label="Questionnaire progress"
            aria-valuemin={1}
            aria-valuemax={questions.length}
            aria-valuenow={currentQuestion + 1}
          >
            <div className="progress-fill" style={{ width: `${progress}%` }}></div>
          </div>
        </div>

        <section className={`question-card ${direction}`} key={currentQuestion} aria-labelledby="question-title">
          <div className="question-header">
            <span className="question-emoji" aria-hidden="true">{q.emoji}</span>
            <h1 id="question-title" ref={headingRef} tabIndex={-1}>{q.title}</h1>
            <p id="question-subtitle">{q.subtitle}</p>
          </div>

          {(q.type === 'multi' || q.type === 'single-grid') && (
            <div className="options-grid" role="group" aria-labelledby="question-title" aria-describedby="question-subtitle">
              {q.options.map(opt => {
                const selected = q.type === 'multi'
                  ? responses[q.field]?.includes(opt.value)
                  : responses[q.field] === opt.value
                return (
                  <button
                    type="button"
                    key={opt.value}
                    className="option-pill"
                    aria-pressed={Boolean(selected)}
                    onClick={() => q.type === 'multi'
                      ? handleMultiSelect(q.field, opt.value)
                      : handleSingleSelect(q.field, opt.value, false)
                    }
                  >
                    <span className="option-icon" aria-hidden="true">{opt.icon}</span>
                    <span>{opt.label}</span>
                    <Check />
                  </button>
                )
              })}
            </div>
          )}

          {q.type === 'single' && (
            <div className="options-stack" role="group" aria-labelledby="question-title" aria-describedby="question-subtitle">
              {q.options.map(opt => (
                <button
                  type="button"
                  key={opt.value}
                  className="option-card"
                  aria-pressed={responses[q.field] === opt.value}
                  onClick={() => handleSingleSelect(q.field, opt.value)}
                >
                  <span className="option-card-icon" aria-hidden="true">{opt.icon}</span>
                  <span className="option-card-content">
                    <span className="option-card-title">{opt.label}</span>
                    <span className="option-card-desc">{opt.desc}</span>
                  </span>
                  <Check />
                </button>
              ))}
            </div>
          )}

          {q.type === 'sliders' && (
            <div className="slider-group">
              {q.sliders.map(slider => (
                <div key={slider.key} className="slider-item">
                  <div className="slider-header">
                    <label className="slider-label" htmlFor={slider.key}>
                      <span aria-hidden="true">{slider.icon} </span>{slider.label}
                    </label>
                    <span className="slider-value" aria-hidden="true">{responses[slider.key]}</span>
                  </div>
                  <p className="slider-desc" id={`${slider.key}-desc`}>{slider.desc}</p>
                  <input
                    id={slider.key}
                    type="range"
                    min="1"
                    max="5"
                    step="1"
                    value={responses[slider.key]}
                    onChange={(e) => handleSlider(slider.key, e.target.value)}
                    aria-describedby={`${slider.key}-desc`}
                    aria-valuetext={`${responses[slider.key]} out of 5`}
                    className="slider"
                  />
                  <div className="slider-labels" aria-hidden="true">
                    <span>Not important</span>
                    <span>Very important</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {q.type === 'multi' && (
          <p className="hint-text" aria-live="polite">
            {selectedCount ? `${selectedCount} selected` : 'Pick at least one to continue'}
          </p>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}

        <div className="nav-buttons">
          <button type="button" className="btn btn-secondary" onClick={goBack} disabled={currentQuestion === 0}>
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            Back
          </button>

          {!isLast ? (
            <button type="button" className="btn btn-primary" onClick={goNext} disabled={!valid}>
              Next
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={submit} disabled={isLoading} aria-busy={isLoading}>
              {isLoading ? <><span className="spinner" aria-hidden="true"></span>Saving…</> : <>Finish</>}
            </button>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
