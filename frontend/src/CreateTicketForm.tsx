import { useState } from 'react'
import type { FormEvent } from 'react'

type CreateTicketFormProps = {
  onCreated: () => void
}

export default function CreateTicketForm({
  onCreated,
}: CreateTicketFormProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (submitting) return

    setError('')
    setSuccess('')

    const cleanTitle = title.trim()
    const cleanDescription = description.trim()

    if (cleanTitle.length < 5 || cleanDescription.length < 10) {
      setError(
        'Enter a title of at least 5 characters and a description of at least 10 characters.',
      )
      return
    }

    setSubmitting(true)

    try {
      const response = await fetch('/api/tickets', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: cleanTitle,
          description: cleanDescription,
        }),
      })

      if (!response.ok) {
        throw new Error(`Could not create ticket (${response.status}).`)
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Could not reach the server.',
      )
      setSubmitting(false)
      return
    }

    setTitle('')
    setDescription('')
    setSuccess('Ticket created successfully.')
    setSubmitting(false)
    onCreated()
  }

  return (
    <section aria-labelledby="create-ticket-heading">
      <h2 id="create-ticket-heading">Create a ticket</h2>

      <form onSubmit={handleSubmit}>
        <fieldset disabled={submitting}>
          <legend>Describe your issue</legend>

          <p>
            <label htmlFor="ticket-title">Title</label>
            <br />
            <input
              id="ticket-title"
              name="title"
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              minLength={5}
              maxLength={150}
              placeholder="Cannot access premium features"
              required
            />
          </p>

          <p>
            <label htmlFor="ticket-description">Description</label>
            <br />
            <textarea
              id="ticket-description"
              name="description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              minLength={10}
              maxLength={5000}
              rows={5}
              placeholder="Tell us what happened and what you expected."
              required
            />
          </p>

          <button type="submit">
            {submitting ? 'Creating...' : 'Create ticket'}
          </button>
        </fieldset>

        {error && <p role="alert">{error}</p>}
        {success && <p role="status">{success}</p>}
      </form>
    </section>
  )
}