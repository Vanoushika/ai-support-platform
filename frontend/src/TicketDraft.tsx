import { useState } from 'react'

type Source = {
  filename: string
  article_id: string
  content: string
  similarity: number
}

type DraftResponse = {
  ticket_id: string
  draft: string
  sources: Source[]
  review_warnings: string[]
  requires_review: true
  context_used: boolean
  grounding_verified: false
}

type TicketDraftProps = {
  ticketId: string
}

export default function TicketDraft({ ticketId }: TicketDraftProps) {
  const [result, setResult] = useState<DraftResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function generateDraft() {
    if (loading) return

    setLoading(true)
    setError('')

    try {
      const response = await fetch(
        `/api/tickets/${ticketId}/draft`,
        { method: 'POST' },
      )

      if (!response.ok) {
        let message = `Could not generate draft (${response.status}).`

        try {
          const body = await response.json()

          if (typeof body.detail === 'string') {
            message = body.detail
          }
        } catch {
          // Use the fallback message if the error isn't JSON.
        }

        throw new Error(message)
      }

      const data = await response.json()

      if (
        typeof data.draft !== 'string' ||
        !data.draft.trim() ||
        !Array.isArray(data.sources) ||
        !Array.isArray(data.review_warnings)
      ) {
        throw new Error('The server returned an invalid draft response.')
      }

      setResult(data as DraftResponse)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not reach the server.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="draft-panel" aria-label="AI response draft">
      <button
        type="button"
        onClick={() => void generateDraft()}
        disabled={loading}
      >
        {loading
          ? 'Generating...'
          : result
            ? 'Regenerate AI draft'
            : 'Generate AI draft'}
      </button>

      {loading && (
        <p role="status">
          Searching documents and preparing a response...
        </p>
      )}

      {error && <p role="alert">{error}</p>}

      {result && (
        <>
          <h3>Suggested response</h3>

          <p className="draft-notice">
            Human review required. Retrieved documents were supplied
            to the model, but the answer has not been verified.
            This draft has not been sent or saved.
          </p>

          {result.review_warnings.length > 0 ? (
            <div role="alert">
              <strong>Review checks flagged:</strong>
              <ul>
                {result.review_warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p>
              No issues found by the limited automated checks.
              This does not guarantee accuracy.
            </p>
          )}

          <div className="draft-text">{result.draft}</div>

          <h3>Retrieved sources</h3>

          <p>
            These are the articles supplied to the model.
            Similarity measures retrieval ranking, not answer accuracy.
          </p>

          {result.sources.map((source) => (
            <details key={source.filename}>
              <summary>
                {source.article_id} — {source.filename}
                {' · '}
                Similarity: {source.similarity.toFixed(3)}
              </summary>

              <div className="draft-text">{source.content}</div>
            </details>
          ))}
        </>
      )}
    </section>
  )
}