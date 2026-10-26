import { useEffect, useState } from 'react'

type RoutingDecision = {
  ticket_id: string
  category: string
  reason: string
  queue: string
  requires_human_review: boolean
  review_reason: string
  routed_at: string
}

type TicketRoutingProps = {
  ticketId: string
}

export default function TicketRouting({
  ticketId,
}: TicketRoutingProps) {
  const [decision, setDecision] = useState<RoutingDecision | null>(null)
  const [loading, setLoading] = useState(true)
  const [routing, setRouting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    async function loadRouting() {
      setLoading(true)
      setError('')

      try {
        const response = await fetch(
          `/api/tickets/${ticketId}/routing`,
          { signal: controller.signal },
        )

        // Existing tickets without a routing decision return 404.
        if (response.status === 404) {
          if (!controller.signal.aborted) {
            setDecision(null)
          }
          return
        }

        if (!response.ok) {
          throw new Error(
            `Could not load routing (${response.status}).`,
          )
        }

        const data: RoutingDecision = await response.json()

        if (!controller.signal.aborted) {
          setDecision(data)
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not load the saved routing decision.',
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadRouting()

    return () => controller.abort()
  }, [ticketId])

  async function routeTicket() {
    if (routing) return

    setRouting(true)
    setError('')

    try {
      const response = await fetch(
        `/api/tickets/${ticketId}/route`,
        { method: 'POST' },
      )

      if (!response.ok) {
        throw new Error(
          `Could not route ticket (${response.status}).`,
        )
      }

      const data: RoutingDecision = await response.json()
      setDecision(data)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not reach the server.',
      )
    } finally {
      setRouting(false)
    }
  }

  return (
    <section className="draft-panel" aria-label="Ticket routing">
      <h3>Support routing</h3>

      {loading && (
        <p role="status">Loading saved routing...</p>
      )}

      {!loading && !decision && !error && (
        <p>This ticket has not been assigned to a queue yet.</p>
      )}

      {decision && (
        <>
          <p>
            <strong>Queue:</strong>{' '}
            {decision.queue.replaceAll('_', ' ')}
          </p>

          <p>
            <strong>Category:</strong>{' '}
            {decision.category.replaceAll('_', ' ')}
          </p>

          <p>{decision.reason}</p>

          {decision.requires_human_review && (
            <p className="draft-notice">
              <strong>Human review required:</strong>{' '}
              {decision.review_reason}
            </p>
          )}

          <p className="ticket-meta">
            Last routed:{' '}
            {new Date(decision.routed_at).toLocaleString()}
          </p>
        </>
      )}

      {error && <p role="alert">{error}</p>}

      <button
        type="button"
        onClick={() => void routeTicket()}
        disabled={loading || routing}
      >
        {routing
          ? 'Classifying and routing...'
          : decision
            ? 'Reclassify ticket'
            : 'Classify and route'}
      </button>

      {routing && (
        <p role="status">
          Assigning a support queue. No customer message is being sent.
        </p>
      )}
    </section>
  )
}