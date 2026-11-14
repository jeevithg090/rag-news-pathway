import { useState, useEffect } from 'react'
import './App.css'

// In dev the questionnaire runs on Vite (:3000) while the main app is served by FastAPI.
// Anonymous user ID shared with the main app through localStorage.
function getOrCreateUserId() {
  let id = localStorage.getItem('news_ai_user_id')
  if (!id) {
    id = 'user_' + Date.now() + '_' + Math.random().toString(36).slice(2, 11)
    localStorage.setItem('news_ai_user_id', id)
  }
  return id
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

  useEffect(() => {
    // Skip the questionnaire if this user already completed it
    fetch(`/api/onboarding/check/${encodeURIComponent(userId)}`)
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        if (data?.completed) window.location.href = MAIN_APP_URL
      })
      .catch(() => { /* backend unreachable: let the user fill the form anyway */ })
  }, [userId])

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
      setTimeout(() => goNext(), 300)
    }
  }

  const handleSlider = (key, value) => {
    setResponses(prev => ({ ...prev, [key]: parseInt(value) }))
  }

  const goNext = () => {
    if (currentQuestion < questions.length - 1) {
      setDirection('next')
      setCurrentQuestion(prev => prev + 1)
    }
  }

  const goBack = () => {
    if (currentQuestion > 0) {
      setDirection('back')
      setCurrentQuestion(prev => prev - 1)
    }
  }

  const isCurrentValid = () => {
    const q = questions[currentQuestion]
    if (q.type === 'sliders') return true
    const val = responses[q.field]
    if (Array.isArray(val)) return val.length > 0
    return val !== null
  }

  const submit = async () => {
    if (!isCurrentValid()) return
    setIsLoading(true)
    setError(null)

    try {
      const payload = {
        user_id: userId,
        ...responses
      }

      const res = await fetch('/api/onboarding', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      const data = await res.json().catch(() => ({}))
      if (res.ok && data.success) {
        setIsComplete(true)
      } else {
        setError(typeof data.detail === 'string' ? data.detail : 'Could not save your answers. Please try again.')
      }
    } catch {
      setError('Could not reach the server. Please check your connection and try again.')
    }
    setIsLoading(false)
  }

  const progress = ((currentQuestion + 1) / questions.length) * 100

  if (isComplete) {
    return (
      <div className="app">
        <div className="bg-effects">
          <div className="gradient-orb orb-1"></div>
          <div className="gradient-orb orb-2"></div>
          <div className="gradient-orb orb-3"></div>
        </div>
        <div className="success-screen">
          <div className="success-icon">🎉</div>
          <h1>You're all set!</h1>
          <p>We've personalized your news experience based on your preferences.</p>
          <button className="btn-primary" onClick={() => window.location.href = MAIN_APP_URL}>
            Start Exploring
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    )
  }

  const q = questions[currentQuestion]

  return (
    <div className="app">
      <div className="bg-effects">
        <div className="gradient-orb orb-1"></div>
        <div className="gradient-orb orb-2"></div>
        <div className="gradient-orb orb-3"></div>
      </div>

      <div className="onboarding-container">
        {/* Progress */}
        <div className="progress-container">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progress}%` }}></div>
          </div>
          <p className="progress-text">Question {currentQuestion + 1} of {questions.length}</p>
        </div>

        {/* Question */}
        <div className={`question-card ${direction}`} key={currentQuestion}>
          <div className="question-header">
            <span className="question-emoji">{q.emoji}</span>
            <h2>{q.title}</h2>
            <p>{q.subtitle}</p>
          </div>

          {/* Multi-select pills */}
          {(q.type === 'multi' || q.type === 'single-grid') && (
            <div className="options-grid">
              {q.options.map(opt => (
                <button
                  key={opt.value}
                  className={`option-pill ${q.type === 'multi'
                    ? (responses[q.field]?.includes(opt.value) ? 'selected' : '')
                    : (responses[q.field] === opt.value ? 'selected' : '')
                    }`}
                  onClick={() => q.type === 'multi'
                    ? handleMultiSelect(q.field, opt.value)
                    : handleSingleSelect(q.field, opt.value, false)
                  }
                >
                  <span className="option-icon">{opt.icon}</span>
                  <span>{opt.label}</span>
                </button>
              ))}
            </div>
          )}

          {/* Single-select cards */}
          {q.type === 'single' && (
            <div className="options-stack">
              {q.options.map(opt => (
                <button
                  key={opt.value}
                  className={`option-card ${responses[q.field] === opt.value ? 'selected' : ''}`}
                  onClick={() => handleSingleSelect(q.field, opt.value)}
                >
                  <div className="option-card-icon">{opt.icon}</div>
                  <div className="option-card-content">
                    <h4>{opt.label}</h4>
                    <p>{opt.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Sliders */}
          {q.type === 'sliders' && (
            <div className="slider-group">
              {q.sliders.map(slider => (
                <div key={slider.key} className="slider-item">
                  <div className="slider-header">
                    <span className="slider-label">{slider.icon} {slider.label}</span>
                    <span className="slider-value">{responses[slider.key]}</span>
                  </div>
                  <p className="slider-desc">{slider.desc}</p>
                  <input
                    type="range"
                    min="1"
                    max="5"
                    value={responses[slider.key]}
                    onChange={(e) => handleSlider(slider.key, e.target.value)}
                    className="slider"
                  />
                  <div className="slider-labels">
                    <span>Not important</span>
                    <span>Very important</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {error && (
          <p className="form-error" role="alert">{error}</p>
        )}

        {/* Navigation */}
        <div className="nav-buttons">
          <button
            className="nav-btn-back"
            onClick={goBack}
            disabled={currentQuestion === 0}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            Back
          </button>

          {currentQuestion < questions.length - 1 ? (
            <button
              className="nav-btn-next"
              onClick={goNext}
              disabled={!isCurrentValid()}
            >
              Next
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          ) : (
            <button
              className="nav-btn-submit"
              onClick={submit}
              disabled={isLoading}
            >
              {isLoading ? 'Saving...' : "Let's Go!"}
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
