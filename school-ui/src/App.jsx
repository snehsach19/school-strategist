import { useState, useEffect, useMemo } from 'react'

const PTA_URL = 'https://losalamitospta.membershiptoolkit.com/home'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001'

// Generate Google Calendar URL
function getGoogleCalendarUrl(event) {
  const name = encodeURIComponent(event.name || 'School Event')
  const date = event.date?.replace(/-/g, '') || ''

  // If there's a time, use it; otherwise make it all-day
  let dates
  if (event.time) {
    // Parse time like "6:00 PM" or "10:30 AM"
    const timeMatch = event.time.match(/(\d+):(\d+)\s*(AM|PM)/i)
    if (timeMatch) {
      let hour = parseInt(timeMatch[1])
      const minute = timeMatch[2]
      const ampm = timeMatch[3].toUpperCase()
      if (ampm === 'PM' && hour !== 12) hour += 12
      if (ampm === 'AM' && hour === 12) hour = 0
      const startTime = `${date}T${String(hour).padStart(2, '0')}${minute}00`
      const endHour = hour + 1
      const endTime = `${date}T${String(endHour).padStart(2, '0')}${minute}00`
      dates = `${startTime}/${endTime}`
    } else {
      dates = `${date}/${date}`
    }
  } else {
    // All-day event
    const nextDay = new Date(event.date + 'T00:00:00')
    nextDay.setDate(nextDay.getDate() + 1)
    const nextDayStr = nextDay.toISOString().split('T')[0].replace(/-/g, '')
    dates = `${date}/${nextDayStr}`
  }

  const details = encodeURIComponent(event.description || '')
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${name}&dates=${dates}&details=${details}`
}

// Get event URL (from event or fallback to PTA)
function getEventUrl(event) {
  if (event.url) return event.url

  const name = (event.name || '').toLowerCase()
  const source = event.source || ''

  // PTA events get PTA URL
  if (source === 'pta_website') return PTA_URL

  // Common PTA event keywords
  const ptaKeywords = ['dance', 'variety show', 'book fair', 'movie night', 'bingo', 'fundraiser']
  if (ptaKeywords.some(k => name.includes(k))) return PTA_URL

  return null
}

function App() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedDay, setSelectedDay] = useState('today')
  const [weekOffset, setWeekOffset] = useState(0)  // 0 = this week, 1 = next week, -1 = last week
  const [filter, setFilter] = useState('all')  // all, events, meals, noschool
  const [calendarMonth, setCalendarMonth] = useState(new Date().getMonth())
  const [calendarYear, setCalendarYear] = useState(new Date().getFullYear())
  const [selectedCalendarDate, setSelectedCalendarDate] = useState(null)
  const [question, setQuestion] = useState('')
  const [aiAnswer, setAiAnswer] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [customTodos, setCustomTodos] = useState(() => {
    // Load from localStorage on init
    const saved = localStorage.getItem('parentTodos')
    return saved ? JSON.parse(saved) : []
  })

  // Save custom todos to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('parentTodos', JSON.stringify(customTodos))
  }, [customTodos])

  const addToTodo = (event) => {
    // Don't add duplicates
    if (customTodos.some(t => t.name === event.name && t.date === event.date)) return
    setCustomTodos([...customTodos, {
      name: event.name,
      date: event.date,
      description: event.description,
      addedAt: new Date().toISOString()
    }])
  }

  const removeFromTodo = (index) => {
    setCustomTodos(customTodos.filter((_, i) => i !== index))
  }

  const isInTodo = (event) => {
    return customTodos.some(t => t.name === event.name && t.date === event.date)
  }

  const askAssistant = async () => {
    if (!question.trim()) return
    setAiLoading(true)
    setAiAnswer('')
    try {
      const res = await fetch(`${API_URL}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() })
      })
      const data = await res.json()
      if (data.error) {
        setAiAnswer(`Error: ${data.error}`)
      } else {
        setAiAnswer(data.answer)
      }
    } catch (err) {
      setAiAnswer('Could not connect to the assistant. Make sure the API server is running.')
    }
    setAiLoading(false)
  }

  useEffect(() => {
    // Try API first, fallback to local file for development
    fetch(`${API_URL}/api/events`)
      .then(res => {
        if (!res.ok) throw new Error('API not available')
        return res.json()
      })
      .then(data => {
        setEvents(data)
        setLoading(false)
      })
      .catch(() => {
        // Fallback to local file
        fetch('/events.json')
          .then(res => res.json())
          .then(data => {
            setEvents(data)
            setLoading(false)
          })
          .catch(err => {
            setError(err.message)
            setLoading(false)
          })
      })
  }, [])

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const todayStr = today.toISOString().split('T')[0]

  // Get start of week (Monday) with offset
  // On weekends (Sat/Sun), automatically show next week
  const startOfWeek = useMemo(() => {
    const d = new Date(today)
    const day = d.getDay()

    // Calculate Monday of current week
    const diff = d.getDate() - day + (day === 0 ? -6 : 1)
    d.setDate(diff + (weekOffset * 7))

    // On weekends with no offset, show next week instead
    if (weekOffset === 0 && (day === 0 || day === 6)) {
      d.setDate(d.getDate() + 7)
    }

    return d
  }, [today, weekOffset])

  // Week dates (Mon-Fri)
  const weekDates = useMemo(() => {
    return Array.from({ length: 5 }, (_, i) => {
      const d = new Date(startOfWeek)
      d.setDate(d.getDate() + i)
      return d
    })
  }, [startOfWeek])

  // Week label
  const isWeekend = today.getDay() === 0 || today.getDay() === 6
  const weekLabel = useMemo(() => {
    if (weekOffset === 0 && isWeekend) return 'Next Week'
    if (weekOffset === 0) return 'This Week'
    if (weekOffset === 1) return isWeekend ? 'Week After Next' : 'Next Week'
    if (weekOffset === -1) return isWeekend ? 'This Week' : 'Last Week'
    const start = weekDates[0]
    return `Week of ${start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
  }, [weekOffset, weekDates, isWeekend])

  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

  // Helper to get events for a specific date
  const getEventsForDate = (date) => {
    const dateStr = date.toISOString().split('T')[0]
    return events.filter(e => e.date === dateStr)
  }

  // Get the actual selected date object
  const getSelectedDate = () => {
    if (selectedDay === 'today') return today
    if (typeof selectedDay === 'number') return weekDates[selectedDay]
    return today
  }

  const selectedDate = getSelectedDate()
  const selectedEvents = getEventsForDate(selectedDate)

  // Split events by type
  const breakfast = selectedEvents.find(e => e.type === 'breakfast_menu')
  const lunch = selectedEvents.find(e => e.type === 'lunch_menu')
  const allDayEvents = selectedEvents.filter(e => e.type === 'event' || e.type === 'deadline')

  // Apply filter to day events
  const dayEvents = allDayEvents.filter(e => {
    if (filter === 'all') return true
    if (filter === 'events') return true
    if (filter === 'noschool') {
      const n = (e.name || '').toLowerCase()
      return n.includes('no school') || n.includes('recess') || n.includes('holiday')
    }
    return false
  })

  // Should show meals based on filter
  const showMeals = filter === 'all' || filter === 'meals'

  // Parent Action Items - events in next 14 days that require parent action
  const parentActionItems = useMemo(() => {
    const twoWeeksFromNow = new Date(today)
    twoWeeksFromNow.setDate(twoWeeksFromNow.getDate() + 14)
    const twoWeeksStr = twoWeeksFromNow.toISOString().split('T')[0]

    // Action keywords that indicate parent needs to do something
    const actionKeywords = ['bring', 'send', 'wear', 'prepare', 'buy', 'make', 'order', 'sign up', 'register', 'rsvp', 'submit', 'return', 'pack', 'label']

    return events
      .filter(e => {
        if (e.type !== 'event' && e.type !== 'deadline') return false
        if (!e.date || e.date < todayStr || e.date > twoWeeksStr) return false

        const desc = (e.description || '').toLowerCase()
        const hasAction = actionKeywords.some(kw => desc.includes(kw))
        return hasAction
      })
      .map(e => {
        const eventDate = new Date(e.date + 'T00:00:00')
        const daysUntil = Math.ceil((eventDate - today) / (1000 * 60 * 60 * 24))
        return { ...e, daysUntil }
      })
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 5)
  }, [events, todayStr, today])

  // Upcoming events with filter
  const upcomingEvents = useMemo(() => {
    let filtered = events.filter(e => e.date >= todayStr)

    if (filter === 'all') {
      filtered = filtered.filter(e => e.type === 'event' || e.type === 'deadline')
    } else if (filter === 'events') {
      filtered = filtered.filter(e => e.type === 'event' || e.type === 'deadline')
    } else if (filter === 'meals') {
      filtered = filtered.filter(e => e.type === 'lunch_menu' || e.type === 'breakfast_menu')
    } else if (filter === 'noschool') {
      filtered = filtered.filter(e => {
        const n = (e.name || '').toLowerCase()
        return n.includes('no school') || n.includes('recess') || n.includes('holiday')
      })
    }

    return filtered
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 12)
  }, [events, todayStr, filter])

  // Format date for display
  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    })
  }

  const formatEventDate = (dateStr, endDateStr = null, dateDisplay = null) => {
    // Use pre-formatted date range if available
    if (dateDisplay) return dateDisplay

    const d = new Date(dateStr + 'T00:00:00')

    // If there's an end date, format as range
    if (endDateStr && endDateStr !== dateStr) {
      const end = new Date(endDateStr + 'T00:00:00')
      if (d.getMonth() === end.getMonth()) {
        return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}-${end.getDate()}`
      }
      return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${end.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
    }

    if (d.toDateString() === today.toDateString()) return 'Today'
    const tomorrow = new Date(today)
    tomorrow.setDate(tomorrow.getDate() + 1)
    if (d.toDateString() === tomorrow.toDateString()) return 'Tomorrow'
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
  }

  // Menu icon helper - matches food to emoji
  const getMenuIcon = (description, isBreakfast = false) => {
    const d = (description || '').toLowerCase()

    // Breakfast items
    if (d.includes('pancake')) return '🥞'
    if (d.includes('waffle')) return '🧇'
    if (d.includes('french toast')) return '🍞'
    if (d.includes('cereal')) return '🥣'
    if (d.includes('muffin')) return '🧁'
    if (d.includes('bagel')) return '🥯'
    if (d.includes('egg') || d.includes('omelet')) return '🍳'
    if (d.includes('yogurt')) return '🥛'
    if (d.includes('donut') || d.includes('doughnut')) return '🍩'

    // Lunch items
    if (d.includes('pizza')) return '🍕'
    if (d.includes('burger') || d.includes('hamburger')) return '🍔'
    if (d.includes('hot dog')) return '🌭'
    if (d.includes('taco')) return '🌮'
    if (d.includes('burrito')) return '🌯'
    if (d.includes('sandwich') || d.includes('sub')) return '🥪'
    if (d.includes('chicken nugget') || d.includes('nuggets')) return '🍗'
    if (d.includes('chicken')) return '🍗'
    if (d.includes('pasta') || d.includes('spaghetti') || d.includes('noodle')) return '🍝'
    if (d.includes('mac') && d.includes('cheese')) return '🧀'
    if (d.includes('salad')) return '🥗'
    if (d.includes('soup')) return '🍲'
    if (d.includes('rice')) return '🍚'
    if (d.includes('fish') || d.includes('seafood')) return '🐟'
    if (d.includes('corn dog')) return '🌭'
    if (d.includes('quesadilla')) return '🫓'
    if (d.includes('nachos')) return '🧀'
    if (d.includes('popcorn chicken')) return '🍿'

    // Default icons
    return isBreakfast ? '🥞' : '🍽️'
  }

  // Event icon helper
  const getEventIcon = (name) => {
    const n = (name || '').toLowerCase()
    if (n.includes('dance')) return '💃'
    if (n.includes('spirit')) return '🎉'
    if (n.includes('book fair')) return '📚'
    if (n.includes('picture')) return '📷'
    if (n.includes('concert') || n.includes('performance')) return '🎵'
    if (n.includes('recess') || n.includes('no school') || n.includes('holiday')) return '🏖️'
    if (n.includes('meeting')) return '👥'
    if (n.includes('tour')) return '🏫'
    if (n.includes('variety show')) return '🎭'
    return '📅'
  }

  // Event Card Component
  const EventCard = ({ event, showDate = false }) => {
    const url = getEventUrl(event)
    const calUrl = getGoogleCalendarUrl(event)
    const [showFlyer, setShowFlyer] = useState(false)

    return (
      <div className="p-4 rounded-lg border-l-4 bg-gray-50 border-indigo-400">
        <div className="flex items-start gap-3 min-w-0">
          <span className="text-xl flex-shrink-0">{getEventIcon(event.name)}</span>
          <div className="min-w-0 flex-1">
            <p className="font-medium text-gray-900">{event.name}</p>
            {showDate && (
              <p className="text-sm text-gray-500 mt-0.5">{formatEventDate(event.date, event.end_date, event.date_display)}</p>
            )}
            {event.time && (
              <p className="text-sm text-gray-500 mt-0.5">🕐 {event.time}</p>
            )}
            {event.location && (
              <p className="text-sm text-gray-500 mt-0.5">📍 {event.location}</p>
            )}
            {event.description && (
              <p className="text-sm text-gray-600 mt-1 line-clamp-2">{event.description}</p>
            )}
            {/* Action Links */}
            <div className="flex flex-wrap gap-3 mt-2">
              {url && (
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
                >
                  Details →
                </a>
              )}
              <a
                href={calUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                + Calendar
              </a>
              {isInTodo(event) ? (
                <span className="text-sm text-green-600">✓ In To-Do</span>
              ) : (
                <button
                  onClick={() => addToTodo(event)}
                  className="text-sm text-amber-600 hover:text-amber-700"
                >
                  + To-Do
                </button>
              )}
              {event.image_url && (
                <button
                  onClick={() => setShowFlyer(!showFlyer)}
                  className="text-sm text-indigo-500 hover:text-indigo-700"
                >
                  {showFlyer ? '▲ Hide Flyer' : '🖼️ View Flyer'}
                </button>
              )}
            </div>
            {/* Flyer Image */}
            {event.image_url && showFlyer && (
              <div className="mt-3">
                <img
                  src={event.image_url}
                  alt={`${event.name} flyer`}
                  className="max-w-full rounded-lg shadow-sm border border-gray-200"
                  style={{ maxHeight: '400px' }}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-gray-500">Loading...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-red-100 text-red-700 p-6 rounded-lg max-w-md">
          <h2 className="font-bold mb-2">Error</h2>
          <p>{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-indigo-600 text-white px-4 py-5 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-2xl lg:text-3xl font-bold">Los Alamitos Elementary Smart Calendar</h1>
          <p className="text-indigo-200 mt-1">All your school events, menus, and updates in one place</p>
          <p className="text-indigo-300 text-sm mt-1">{formatDate(today)}</p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 lg:px-8">
        {/* Ask Assistant */}
        <div className="mb-6 bg-white rounded-xl shadow-sm p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xl">🤖</span>
            <span className="font-medium text-gray-700">Ask Assistant</span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="e.g., When is pizza coming up?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && askAssistant()}
              className="flex-1 px-4 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
            <button
              onClick={askAssistant}
              disabled={aiLoading || !question.trim()}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {aiLoading ? '...' : 'Ask'}
            </button>
          </div>
          {aiAnswer && (
            <div className="mt-3 p-3 bg-gray-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap">
              {aiAnswer}
            </div>
          )}
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
          {[
            { id: 'all', label: 'All' },
            { id: 'events', label: 'Events' },
            { id: 'meals', label: 'Meals' },
            { id: 'noschool', label: 'No School' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                filter === tab.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Week Section */}
        <section className="mb-8">
          {/* Week Header with Navigation */}
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-800">{weekLabel}</h2>
            <div className="flex gap-1">
              <button
                onClick={() => { setWeekOffset(w => w - 1); setSelectedDay(0); }}
                className="px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                ← Prev
              </button>
              {weekOffset !== 0 && (
                <button
                  onClick={() => { setWeekOffset(0); setSelectedDay('today'); }}
                  className="px-3 py-1 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg font-medium"
                >
                  Today
                </button>
              )}
              <button
                onClick={() => { setWeekOffset(w => w + 1); setSelectedDay(0); }}
                className="px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                Next →
              </button>
            </div>
          </div>

          {/* Week Strip - Grid layout to fit all days without scrolling */}
          <div className="grid grid-cols-5 gap-1 sm:gap-2 mb-4">
            {weekDates.map((date, i) => {
              const isSelected = selectedDay === i || (selectedDay === 'today' && date.toDateString() === today.toDateString())
              const dateEvents = getEventsForDate(date)
              const hasEvents = dateEvents.some(e => e.type === 'event' || e.type === 'deadline')
              const isToday = date.toDateString() === today.toDateString()

              return (
                <button
                  key={i}
                  onClick={() => setSelectedDay(i)}
                  className={`flex flex-col items-center py-2 px-1 sm:px-3 rounded-lg text-xs sm:text-sm font-medium transition-colors ${
                    isSelected
                      ? 'bg-indigo-600 text-white'
                      : isToday
                        ? 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'
                        : 'bg-white text-gray-700 hover:bg-gray-100'
                  } shadow-sm relative`}
                >
                  <span className="text-[10px] sm:text-xs uppercase tracking-wide opacity-75">{dayNames[i]}</span>
                  <span className="text-base sm:text-lg font-bold">{date.getDate()}</span>
                  <span className="text-[10px] sm:text-xs opacity-75 hidden sm:block">{date.toLocaleDateString('en-US', { month: 'short' })}</span>
                  {hasEvents && (
                    <span className={`absolute top-1 right-1 w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-yellow-300' : 'bg-indigo-500'}`}></span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Selected Day Detail */}
          <div className="bg-white rounded-xl shadow-sm p-5">
            <h3 className="text-base font-semibold text-gray-600 mb-4">
              {selectedDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </h3>

            {/* Meals - Side by Side */}
            {showMeals && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
                <div className="bg-amber-50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">{getMenuIcon(breakfast?.description, true)}</span>
                    <span className="font-semibold text-amber-800">Breakfast</span>
                  </div>
                  <p className="text-sm text-amber-900">
                    {breakfast?.description || 'No menu available'}
                  </p>
                </div>
                <div className="bg-orange-50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">{getMenuIcon(lunch?.description, false)}</span>
                    <span className="font-semibold text-orange-800">Lunch</span>
                  </div>
                  <p className="text-sm text-orange-900">
                    {lunch?.description || 'No menu available'}
                  </p>
                </div>
              </div>
            )}

            {/* Day Events */}
            {filter !== 'meals' && (
              dayEvents.length > 0 ? (
                <div>
                  <div className="flex items-center gap-2 mb-3 text-gray-600">
                    <span>📅</span>
                    <span className="font-medium">Events</span>
                  </div>
                  <div className="space-y-3">
                    {dayEvents.map((ev, i) => (
                      <EventCard key={i} event={ev} />
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-400 italic">
                  {filter === 'noschool' ? 'School is in session this day' : 'No events scheduled for this day'}
                </p>
              )
            )}
          </div>
        </section>

        {/* Parent To-Do Section */}
        {(parentActionItems.length > 0 || customTodos.length > 0) && (
          <section className="mb-8">
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <h2 className="text-base font-semibold text-amber-800 mb-3 flex items-center gap-2">
                <span>📋</span> Parent To-Do
              </h2>
              <div className="space-y-2">
                {/* Auto-detected action items */}
                {parentActionItems.map((item, i) => (
                  <div key={`auto-${i}`} className="bg-white rounded-lg p-3 shadow-sm">
                    <div className="flex justify-between items-start gap-2">
                      <div className="flex-1">
                        <div className="font-medium text-gray-800 text-sm">{item.name}</div>
                        <div className="text-sm text-gray-600 mt-1">{item.description}</div>
                      </div>
                      <div className="text-xs font-medium px-2 py-1 rounded-full bg-amber-100 text-amber-700 whitespace-nowrap">
                        {item.daysUntil === 0 ? 'Today' : item.daysUntil === 1 ? 'Tomorrow' : `${item.daysUntil} days`}
                      </div>
                    </div>
                  </div>
                ))}
                {/* Custom todos added by user */}
                {customTodos.map((item, i) => {
                  const eventDate = item.date ? new Date(item.date + 'T00:00:00') : null
                  const daysUntil = eventDate ? Math.ceil((eventDate - today) / (1000 * 60 * 60 * 24)) : null
                  return (
                    <div key={`custom-${i}`} className="bg-white rounded-lg p-3 shadow-sm border-l-4 border-indigo-400">
                      <div className="flex justify-between items-start gap-2">
                        <div className="flex-1">
                          <div className="font-medium text-gray-800 text-sm">{item.name}</div>
                          {item.description && <div className="text-sm text-gray-600 mt-1">{item.description}</div>}
                        </div>
                        <div className="flex items-center gap-2">
                          {daysUntil !== null && (
                            <div className="text-xs font-medium px-2 py-1 rounded-full bg-indigo-100 text-indigo-700 whitespace-nowrap">
                              {daysUntil <= 0 ? 'Past' : daysUntil === 1 ? 'Tomorrow' : `${daysUntil} days`}
                            </div>
                          )}
                          <button
                            onClick={() => removeFromTodo(i)}
                            className="text-gray-400 hover:text-red-500 text-lg leading-none"
                            title="Remove from to-do"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </section>
        )}

        {/* Upcoming Events */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">
            {filter === 'all' ? 'Upcoming Events' :
             filter === 'events' ? 'Upcoming Events' :
             filter === 'meals' ? 'Upcoming Meals' :
             filter === 'noschool' ? 'No School Days' : 'Upcoming'}
          </h2>
          <div className="space-y-3">
            {upcomingEvents.length === 0 ? (
              <div className="bg-white rounded-xl shadow-sm p-5 text-gray-400 text-sm">
                No upcoming events
              </div>
            ) : (
              upcomingEvents.map((ev, i) => (
                <EventCard key={i} event={ev} showDate={true} />
              ))
            )}
          </div>
        </section>

        {/* Calendar View (Collapsible) */}
        <section className="mb-8">
          <details className="bg-white rounded-xl shadow-sm">
            <summary className="p-4 cursor-pointer font-medium text-gray-700 hover:bg-gray-50 rounded-xl flex items-center gap-2">
              <span>📅</span> View Calendar
            </summary>
            <div className="p-4 pt-0">
              {/* Month Navigation */}
              <div className="flex items-center justify-between mb-3">
                <span className="font-medium text-gray-700">
                  {new Date(calendarYear, calendarMonth).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => {
                      if (calendarMonth === 0) {
                        setCalendarMonth(11)
                        setCalendarYear(y => y - 1)
                      } else {
                        setCalendarMonth(m => m - 1)
                      }
                    }}
                    className="px-2 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded"
                  >
                    ←
                  </button>
                  <button
                    onClick={() => {
                      setCalendarMonth(new Date().getMonth())
                      setCalendarYear(new Date().getFullYear())
                    }}
                    className="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 rounded"
                  >
                    Today
                  </button>
                  <button
                    onClick={() => {
                      if (calendarMonth === 11) {
                        setCalendarMonth(0)
                        setCalendarYear(y => y + 1)
                      } else {
                        setCalendarMonth(m => m + 1)
                      }
                    }}
                    className="px-2 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded"
                  >
                    →
                  </button>
                </div>
              </div>

              {/* Calendar Grid */}
              <div className="border rounded-lg overflow-hidden">
                <div className="grid grid-cols-7 bg-gray-50 border-b">
                  {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map(day => (
                    <div key={day} className="p-1 text-center text-xs font-medium text-gray-500">
                      {day}
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-7">
                  {(() => {
                    const firstDay = new Date(calendarYear, calendarMonth, 1).getDay()
                    const daysInMonth = new Date(calendarYear, calendarMonth + 1, 0).getDate()
                    const cells = []

                    for (let i = 0; i < firstDay; i++) {
                      cells.push(<div key={`e-${i}`} className="p-1 h-8 bg-gray-50" />)
                    }

                    for (let day = 1; day <= daysInMonth; day++) {
                      const dateStr = `${calendarYear}-${String(calendarMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
                      const hasEvents = events.some(e => e.date === dateStr && (e.type === 'event' || e.type === 'deadline'))
                      const isToday = dateStr === todayStr

                      const isSelected = selectedCalendarDate === dateStr

                      cells.push(
                        <div
                          key={day}
                          className={`p-1 h-8 text-center text-sm cursor-pointer hover:bg-indigo-50 border-t ${
                            isSelected ? 'bg-indigo-600 text-white' :
                            isToday ? 'bg-indigo-100 font-bold text-indigo-700' : ''
                          }`}
                          onClick={() => setSelectedCalendarDate(dateStr)}
                        >
                          {day}
                          {hasEvents && !isSelected && <span className="block w-1 h-1 bg-indigo-500 rounded-full mx-auto mt-0.5" />}
                        </div>
                      )
                    }

                    return cells
                  })()}
                </div>
              </div>

              {/* Selected Date Events */}
              {selectedCalendarDate && (
                <div className="mt-4 pt-4 border-t">
                  <h4 className="font-medium text-gray-700 mb-2">
                    {new Date(selectedCalendarDate + 'T00:00:00').toLocaleDateString('en-US', {
                      weekday: 'long',
                      month: 'long',
                      day: 'numeric'
                    })}
                  </h4>
                  {(() => {
                    const dateEvents = events.filter(e => e.date === selectedCalendarDate)
                    const meals = dateEvents.filter(e => e.type === 'lunch_menu' || e.type === 'breakfast_menu')
                    const otherEvents = dateEvents.filter(e => e.type === 'event' || e.type === 'deadline')

                    if (dateEvents.length === 0) {
                      return <p className="text-sm text-gray-400">No events on this day</p>
                    }

                    return (
                      <div className="space-y-2">
                        {meals.map((ev, i) => (
                          <div key={`meal-${i}`} className="flex items-center gap-2 text-sm">
                            <span>{ev.type === 'breakfast_menu' ? getMenuIcon(ev.description, true) : getMenuIcon(ev.description, false)}</span>
                            <span className="font-medium text-gray-600">{ev.type === 'breakfast_menu' ? 'Breakfast:' : 'Lunch:'}</span>
                            <span className="text-gray-700">{ev.description}</span>
                          </div>
                        ))}
                        {otherEvents.map((ev, i) => (
                          <div key={`ev-${i}`} className="flex items-start gap-2 text-sm p-2 bg-gray-50 rounded">
                            <span>{getEventIcon(ev.name)}</span>
                            <div>
                              <span className="font-medium text-gray-900">{ev.name}</span>
                              {ev.time && <span className="text-gray-500 ml-2">{ev.time}</span>}
                              {ev.location && <span className="text-gray-500 ml-2">📍 {ev.location}</span>}
                              {ev.description && <p className="text-gray-600 text-xs mt-0.5">{ev.description}</p>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  })()}
                </div>
              )}
            </div>
          </details>
        </section>

        {/* About Section */}
        <section className="mb-8">
          <details className="bg-white rounded-xl shadow-sm">
            <summary className="p-4 cursor-pointer font-medium text-gray-700 hover:bg-gray-50 rounded-xl">
              About this app
            </summary>
            <div className="px-4 pb-4 text-sm text-gray-600 space-y-3">
              <p>
                <strong>Los Alamitos Smart Calendar</strong> pulls together everything happening at
                Los Alamitos Elementary so you never miss a beat.
              </p>
              <div>
                <p className="font-medium mb-1">Where does the data come from?</p>
                <ul className="list-disc list-inside space-y-1 text-gray-500">
                  <li>ParentSquare emails (school announcements)</li>
                  <li>PTA website (events, sign-ups)</li>
                  <li>SJUSD district calendar (holidays, no-school days)</li>
                  <li>Student Nutrition website (breakfast & lunch menus)</li>
                </ul>
              </div>
              <p>Data refreshes automatically every morning at 6 AM.</p>
              <p className="text-gray-400 italic">Built by Los Alamitos parents, for Los Alamitos parents.</p>
            </div>
          </details>
        </section>

        {/* Footer */}
        <footer className="text-center text-sm text-gray-400 py-6 border-t border-gray-200">
          <p>{events.length} items loaded • Data refreshes daily at 6 AM</p>
        </footer>
      </main>
    </div>
  )
}

export default App
