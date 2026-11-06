import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, Download, FileText, X, BookOpen, ChevronLeft } from 'lucide-react'
import { isAbort, request } from '../api'
import type { PdfSelection, Source } from '../types'
import { EmptyState, ErrorNotice, Spinner } from './ui'

export type EvidenceSelection = { requestId: string } | PdfSelection
export function SourceLinks({
  sources,
  onOpen,
}: {
  sources: Source[]
  onOpen: (source: PdfSelection) => void
}) {
  return (
    <div className="source-links">
      {sources.map((source, index) => (
        <button
          key={`${source.document_id}-${source.page}-${index}`}
          onClick={() => onOpen(source)}
        >
          <FileText size={13} />
          <span>{source.filename}</span>
          <b>p. {source.page}</b>
          <ArrowUpRight size={12} />
        </button>
      ))}
    </div>
  )
}
export default function Evidence({
  selection,
  token,
  userId,
  onClose,
}: {
  selection: EvidenceSelection
  token: string
  userId: string
  onClose: () => void
}) {
  const [page, setPage] = useState<PdfSelection | null>(
    'document_id' in selection ? selection : null,
  )
  useEffect(() => {
    setPage('document_id' in selection ? selection : null)
  }, [selection])
  const sources = useQuery({
    queryKey: ['evidence', userId, 'requestId' in selection ? selection.requestId : null],
    enabled: 'requestId' in selection,
    queryFn: () =>
      request<Source[]>(
        `/chat-runs/${'requestId' in selection ? selection.requestId : ''}/evidence`,
        token,
      ),
  })
  return (
    <aside className="evidence-panel" aria-label="Document viewer">
      <div className="evidence-heading">
        <div>
          <span className="eyebrow">BACK TO THE SOURCE</span>
          <h2>{page ? 'Your document' : 'Supporting notes'}</h2>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close document viewer">
          <X size={19} />
        </button>
      </div>
      {page ? (
        <>
          {'requestId' in selection && (
            <button className="back-link" onClick={() => setPage(null)}>
              <ChevronLeft size={14} />
              All supporting pages
            </button>
          )}
          <PdfViewer selection={page} token={token} />
        </>
      ) : (
        <div className="evidence-body">
          <p className="muted">Explore the pages behind this explanation.</p>
          {sources.isPending ? (
            <Spinner label="Finding supporting pages…" />
          ) : sources.error ? (
            <ErrorNotice error={sources.error} retry={() => void sources.refetch()} />
          ) : sources.data?.length ? (
            sources.data.map((source, index) => (
              <button
                className="source-card"
                key={`${source.document_id}-${source.page}-${index}`}
                onClick={() => setPage(source)}
              >
                <span className="pdf-icon">
                  <FileText size={21} />
                </span>
                <span>
                  <strong>{source.filename}</strong>
                  <small>Page {source.page}</small>
                </span>
                <ArrowUpRight size={17} />
              </button>
            ))
          ) : (
            <EmptyState icon={<BookOpen />} title="No supporting pages">
              This response has no saved document evidence.
            </EmptyState>
          )}
        </div>
      )}
    </aside>
  )
}
function PdfViewer({ selection, token }: { selection: PdfSelection; token: string }) {
  const [url, setUrl] = useState(''),
    [error, setError] = useState<unknown>(null),
    [loading, setLoading] = useState(true),
    [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl = ''
    setLoading(true)
    setError(null)
    setUrl('')
    const suffix = selection.page ? `?page=${selection.page}` : ''
    request<Blob>(`/documents/${encodeURIComponent(selection.document_id)}/file${suffix}`, token, {
      signal: controller.signal,
    })
      .then((blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch((e) => {
        if (!isAbort(e)) setError(e)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [selection.document_id, selection.page, token, retry])
  return (
    <div className="pdf-viewer">
      <div className="pdf-title">
        <FileText size={16} />
        <span title={selection.filename}>{selection.filename}</span>
        {selection.page && <b>Page {selection.page}</b>}
      </div>
      {loading && <Spinner label="Opening your PDF…" />}
      <ErrorNotice error={error} retry={() => setRetry((n) => n + 1)} />
      {url && (
        <>
          <div className="pdf-actions">
            <a className="btn secondary small" href={url} target="_blank" rel="noreferrer">
              <ArrowUpRight size={14} />
              Open PDF
            </a>
            <a
              className="icon-btn"
              href={url}
              download={
                selection.page
                  ? `${selection.filename.replace(/\.pdf$/i, '')}-page-${selection.page}.pdf`
                  : selection.filename
              }
              aria-label="Download PDF"
            >
              <Download size={16} />
            </a>
          </div>
          <iframe
            src={`${url}#toolbar=0&view=FitH`}
            title={`${selection.filename}${selection.page ? ` page ${selection.page}` : ''}`}
          />
          <p className="field-hint">
            If the preview is unavailable on your device, choose Open PDF.
          </p>
        </>
      )}
    </div>
  )
}
