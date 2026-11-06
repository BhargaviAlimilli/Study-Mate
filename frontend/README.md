# Study Mate frontend

React + TypeScript, Vite, TanStack Query, React Markdown, and Lucide icons. This folder contains the interface and its integration tests. No backend files are changed by this setup.

## Run locally

Start the existing backend and its PostgreSQL, Qdrant, Redis, and worker services as described in the root README. The API must be reachable at `http://127.0.0.1:8000`.

In a separate PowerShell terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. Node.js 22.12+ or a supported newer LTS release is required. Sign in using your existing backend account, or create an account in the interface.

Vite proxies `/api/*` to FastAPI and removes the `/api` prefix. No `.env` file is needed for the default local setup. To change the backend target, copy `.env.example` to `.env.local` and edit `API_PROXY_TARGET`. Restart Vite after changing it. Never add database passwords, JWT signing keys, or model API keys here; all `VITE_*` variables are public browser configuration.

## Connected flows

- Registration, login, session expiry, and logout (server token revocation).
- Private PDF library, upload validation, processing status polling, failed-ingestion retry, authenticated viewing and downloads.
- Chat with optional document scope, saved conversations, interrupted-run resume, and separate supporting PDF pages.
- Five-question quizzes, session drafts, idempotent submission retries, saved attempts, explanations, strengths, weaknesses, and PDF links.
- Revision recommendations, reviewed/pending status, targeted practice, historical attempt sync, and recorded progress.
- Browser microphone dictation and synthetic read-aloud without an OpenAI key. Dictation fills the composer for review; sending uses the same grounded chat, provider, and saved conversation flow as a typed question. Browser support varies; microphone permission is required, and the browser provider may process speech on its servers. This is not an offline or continuous real-time audio agent. Unsupported browsers keep text chat available.
- Study image questions and optional audio-file uploads when their server providers are available. Audio-file uploads still require the server's OpenAI transcription configuration; browser dictation does not. Read-aloud prefers browser speech synthesis, with the existing server speech endpoint as a fallback when configured. Image answers are explicitly marked as image-grounded and are not persisted by the existing image endpoint.

The bearer token and unfinished quiz drafts are held in tab-scoped `sessionStorage`. Authentication responses are never logged. API calls use the configured API base only; source URLs from responses are not used as token destinations. PDFs are fetched with authentication and displayed using temporary blob URLs, which are revoked when closed. PDF originals continue to live in the backend database.

The current backend history endpoint does not expose request IDs or quiz attachments on saved messages. Live responses offer supporting pages and quiz cards; saved quizzes and their results remain available in Practice. Historical supporting-page links require an extension to the backend message contract. The interface does not invent those IDs.

## Files

- `src/App.tsx`: session lifecycle, navigation, and shared document drawer.
- `src/api.ts` and `src/types.ts`: authenticated API boundary and response contracts.
- `src/components/`: authentication, library/uploads, chat, evidence/PDF viewer, practice/results, and revisions/progress.
- `src/styles.css`: responsive layouts, typography, focus states, and reduced-motion support.
- `src/test/`: mocked HTTP integration tests. These do not contact model providers or create records in your databases.

## Verify and build

```powershell
npm.cmd test
npm.cmd run build
```

The production files are generated in `dist/`. The Vite development proxy is not a production reverse proxy. For production, serve `/api` through your hosting reverse proxy, or set `VITE_API_BASE_URL` to the deployed API URL before building and configure the backend to allow the frontend origin. `npm run preview` serves build files only and requires a reachable API configuration.

Real upload/chat/quiz generation still depends on healthy backend services and configured model providers. A backend `503 Document search is unavailable` remains an actionable API error; the UI displays it and never substitutes fake answers or scores.
