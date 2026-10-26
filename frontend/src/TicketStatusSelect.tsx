import { useState } from 'react'

type TicketStatus = 'open' | 'in_progress' | 'resolved'

type TicketStatusSelectProps = {
  ticketId: string
  status: TicketStatus
  onUpdated: () => void
}

export default function TicketStatusSelect({
  ticketId,
  status,
  onUpdated,
}: TicketStatusSelectProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function updateStatus(nextStatus: TicketStatus) {
    if (saving || nextStatus === status) return

    setSaving(true)
    setError('')

    try {
      const response = await fetch(
        `/api/tickets/${ticketId}/status`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ status: nextStatus }),
        },
      )

      if (!response.ok) {
        throw new Error(
          `Could not update status (${response.status}).`,
        )
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not reach the server.',
      )
      setSaving(false)
      return
    }

    setSaving(false)
    onUpdated()
  }

  return (
    <div>
      <label htmlFor={`status-${ticketId}`}>
        Status:{' '}
      </label>

      <select
        id={`status-${ticketId}`}
        value={status}
        disabled={saving}
        onChange={(event) =>
          void updateStatus(event.target.value as TicketStatus)
        }
      >
        <option value="open">Open</option>
        <option value="in_progress">In progress</option>
        <option value="resolved">Resolved</option>
      </select>

      {saving && <span role="status"> Saving...</span>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}