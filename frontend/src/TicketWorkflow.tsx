import { useEffect, useState } from 'react'

type Source = {
  article_id: string
  filename: string
  content: string
  similarity: number
}

type WorkflowData = {
  workflow_id: string
  execution_status: string
  phase: string
  decision: string | null
  outcome: {
    decision: string
    reply_sent: boolean
    ticket_resolved: boolean
  } | null
  prepared: {
    draft: {
      draft: string
      review_warnings: string[]
      sources: Source[]
    }
    routing: {
      category: string
      queue: string
      reason: string
      review_reason: string
    }
  } | null
}

type TicketWorkflowProps = {
  ticketId: string
}

const terminalPhases = new Set([
  'completed',
  'failed',
  'canceled',
  'cancelled',
  'terminated',
  'timed_out',
])

async function responseError(response: Response): Promise<string> {
  try {
    const body = await response.json()

    if (typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Fall back to the HTTP status when the response isn't JSON.
  }

  return `Request failed (${response.status}).`
}

export default function TicketWorkflow({
  ticketId,
}: TicketWorkflowProps) {
  const [data, setData] = useState<WorkflowData | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined

    async function loadStatus() {
      try {
        const response = await fetch(
          `/api/tickets/${ticketId}/workflow`,
          { signal: controller.signal },
        )

        if (response.status === 404) {
          if (!controller.signal.aborted) {
            setData(null)
            setError('')
          }
          return
        }

        if (!response.ok) {
          throw new Error(await responseError(response))
        }

        const result: WorkflowData = await response.json()

        if (!controller.signal.aborted) {
          setData(result)
          setError('')

          if (!terminalPhases.has(result.phase)) {
            timer = setTimeout(() => void loadStatus(), 3000)
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not load workflow status.',
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadStatus()

    return () => {
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [ticketId, refreshKey])

  function refreshStatus() {
    setLoading(true)
    setRefreshKey((current) => current + 1)
  }

  async function submitAction(
    action: 'start' | 'approved' | 'rejected',
  ) {
    if (busy || loading) return

    setBusy(true)
    setActionError('')

    const isStart = action === 'start'
    const url = isStart
      ? `/api/tickets/${ticketId}/workflow`
      : `/api/tickets/${ticketId}/workflow/review`

    try {
      const response = await fetch(url, {
        method: 'POST',
        ...(isStart
          ? {}
          : {
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ decision: action }),
            }),
      })

      if (!response.ok) {
        throw new Error(await responseError(response))
      }
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : 'Could not reach the server. Refresh status before retrying.',
      )
    } finally {
      // Also refresh after errors: a timed-out request may have succeeded.
      refreshStatus()
      setBusy(false)
    }
  }

  const prepared = data?.prepared
  const controlsDisabled = loading || busy || Boolean(error)

  return (
    <section className="draft-panel" aria-label="Draft review workflow">
      <h3>AI draft review workflow</h3>

      <p>
        Classify the ticket, prepare a response, and save a human
        review decision. Approval does not send a reply or issue a refund.
      </p>

      {loading && <p role="status">Checking workflow status...</p>}

      {error && <p role="alert">{error}</p>}
      {actionError && <p role="alert">{actionError}</p>}

      {!loading && !error && !data && (
        <>
          <p>No review workflow has been started for this ticket.</p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submitAction('start')}
          >
            {busy ? 'Starting...' : 'Start review workflow'}
          </button>
        </>
      )}

      {data && (
        <>
          <p>
            <strong>Workflow status:</strong>{' '}
            {data.phase.replaceAll('_', ' ')}
          </p>

          {['starting', 'preparing'].includes(data.phase) && (
            <p role="status">
              Classifying the ticket and generating its draft.
              This section updates automatically.
            </p>
          )}

          {prepared && (
            <>
              <p>
                <strong>Assigned queue:</strong>{' '}
                {prepared.routing.queue.replaceAll('_', ' ')}
              </p>

              <p>{prepared.routing.reason}</p>

              <details>
                <summary>Routing review requirements</summary>
                <p>{prepared.routing.review_reason}</p>
              </details>

              <h3>Saved draft</h3>

              <p className="draft-notice">
                Check the response against its sources before approving.
                Automated checks do not guarantee correctness.
              </p>

              {prepared.draft.review_warnings.length > 0 && (
                <div role="alert">
                  <strong>Review warnings</strong>
                  <ul>
                    {prepared.draft.review_warnings.map(
                      (warning, index) => (
                        <li key={index}>{warning}</li>
                      ),
                    )}
                  </ul>
                </div>
              )}

              <div className="draft-text">
                {prepared.draft.draft}
              </div>

              <h3>Retrieved sources</h3>

              {prepared.draft.sources.map((source) => (
                <details key={source.filename}>
                  <summary>
                    {source.article_id} — {source.filename}
                  </summary>

                  <p>
                    Retrieval similarity: {source.similarity.toFixed(3)}
                    {' '}(not an accuracy score).
                  </p>

                  <div className="draft-text">
                    {source.content}
                  </div>
                </details>
              ))}
            </>
          )}

          {data.phase === 'awaiting_review' && prepared && (
            <div style={{ marginTop: 20 }}>
              <p>
                Approve only if you have reviewed this saved draft.
                Reject it if corrections are needed.
              </p>

              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 12,
                }}
              >
                <button
                  type="button"
                  disabled={controlsDisabled}
                  onClick={() => void submitAction('approved')}
                >
                  Approve draft
                </button>

                <button
                  type="button"
                  className="secondary-button"
                  disabled={controlsDisabled}
                  onClick={() => void submitAction('rejected')}
                >
                  Reject draft
                </button>
              </div>
            </div>
          )}

          {busy && <p role="status">Submitting your request...</p>}

          {data.phase === 'recording_decision' && (
            <p role="status">Saving the review decision...</p>
          )}

          {data.phase === 'completed' && (
            <div role="status">
              <p>
                <strong>Review decision:</strong> {data.decision}
              </p>
              <p>
                Decision saved. No customer reply or refund was sent.
                Ticket status remains separate.
              </p>
            </div>
          )}

          {terminalPhases.has(data.phase) &&
            data.phase !== 'completed' && (
              <p role="alert">
                The workflow ended without completing the review.
                Check its history in the Temporal dashboard.
              </p>
            )}
        </>
      )}

      <div style={{ marginTop: 16 }}>
        <button
          type="button"
          className="secondary-button"
          onClick={refreshStatus}
          disabled={loading || busy}
        >
          Refresh workflow status
        </button>
      </div>
    </section>
  )
}