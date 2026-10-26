import { useEffect, useState } from 'react'
import CreateTicketForm from './CreateTicketForm'
import TicketStatusSelect from './TicketStatusSelect'
import TicketWorkflow from './TicketWorkflow'

type Ticket = {
  id: string
  title: string
  description: string
  status: 'open' | 'in_progress' | 'resolved'
  created_at: string
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    async function loadTickets() {
      setLoading(true)
      setError('')

      try {
        const response = await fetch('/api/tickets', {
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(
            `Could not load tickets (${response.status}).`,
          )
        }

        const result: Ticket[] = await response.json()

        if (!controller.signal.aborted) {
          setTickets(result)
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not load tickets.',
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadTickets()

    return () => controller.abort()
  }, [refreshKey])

  function refreshTickets() {
    setRefreshKey((current) => current + 1)
  }

  return (
    <main>
      <header className="page-header">
        <span className="eyebrow">SUPPORT WORKSPACE</span>
        <h1>AI Support Platform</h1>
        <p>
          Manage tickets, prepare grounded drafts, and review responses.
        </p>
      </header>

      <CreateTicketForm onCreated={refreshTickets} />

      <div className="tickets-heading">
        <h2>All tickets</h2>

        <button
          type="button"
          className="secondary-button"
          onClick={refreshTickets}
          disabled={loading}
        >
          Refresh tickets
        </button>
      </div>

      {loading && <p role="status">Loading tickets...</p>}

      {error && (
        <div role="alert">
          <p>{error}</p>
          <button type="button" onClick={refreshTickets}>
            Retry loading tickets
          </button>
        </div>
      )}

      {!loading && !error && tickets.length === 0 && (
        <p>No tickets yet. Create your first ticket above.</p>
      )}

      {tickets.map((ticket) => (
        <article key={ticket.id}>
          <h2>{ticket.title}</h2>
          <p>{ticket.description}</p>

          <TicketStatusSelect
            ticketId={ticket.id}
            status={ticket.status}
            onUpdated={refreshTickets}
          />

          <p className="ticket-meta">
            Created: {new Date(ticket.created_at).toLocaleString()}
          </p>

          <TicketWorkflow ticketId={ticket.id} />
        </article>
      ))}
    </main>
  )
}