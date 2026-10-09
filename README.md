# Personal Study App

A single-user, self-hosted study application with JSON import and FSRS spaced repetition.

## Run it

Requirements: Docker with the Compose plugin.

```bash
docker compose up -d --build
```

Open <http://localhost:3000>. The API health endpoint is available at
<http://localhost:8000/api/health>.

To load the included sample, open **Import**, select
`sample-data/efes_memories.json`, and submit it. Importing it again is safe: its
existing `external_id` values will be reported as duplicates.

The Import page also accepts a folder. Every `.json` file in the selected
directory tree is processed independently; unrelated files are ignored and a
malformed JSON file does not prevent the remaining valid files from importing.

## Generate questions from a PDF

Question generation uses OpenRouter from the FastAPI backend. The API key is
never sent to the browser and generated questions are previewed before anything
is written to PostgreSQL.

1. Create an API key in the [OpenRouter Keys dashboard](https://openrouter.ai/settings/keys).
2. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

3. Set `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and optionally
   `OPENROUTER_BASE_URL`, `OPENROUTER_TIMEOUT_SECONDS`,
   `OPENROUTER_MAX_COMPLETION_TOKENS`, and `API_PROXY_TIMEOUT_MS` in `.env`.
   The provider timeout defaults to 300 seconds, the completion budget defaults
   to 32,000 tokens, and the frontend proxy defaults to 330 seconds. Completion
   tokens include model reasoning as well as visible JSON. The model is
   configurable; confirm that the chosen OpenRouter model supports structured
   output and has enough context and output capacity for the lecture PDF. The
   default is `anthropic/claude-haiku-5.5`.
4. Rebuild/start the stack with `docker compose up -d --build`.
5. Open **Generate**, select an existing subject and model, choose a text-based
   PDF, review the input estimate, and generate. The model selector includes
   common presets and accepts any OpenRouter model ID through **Custom model…**.
6. Inspect every generated section. Use **Import all** only after the preview is
   satisfactory, or download individual schema-1.0 JSON files for later use.

The preview endpoint validates every generated section with the same import
schema used by manual JSON import. Approval reuses the batch importer, including
its `external_id` duplicate handling. Scanned image-only PDFs are not OCRed and
must be converted to searchable text first. OpenRouter is an external paid
service; generation may incur charges under the selected model's current
pricing. The app shows an approximate token count but does not hard-code prices.

Generation endpoints:

```text
GET  /api/generate/config
POST /api/generate/estimate
POST /api/generation
```

### Lecture PDF storage

PDFs submitted for generation are stored by SHA-256 and registered as lecture
sources before the OpenRouter request. Re-uploading the same PDF for the same
subject reuses its source record. Generated questions receive the source link
only when the preview is approved; manual JSON imports continue to work without
a stored PDF.

Lecture metadata lives in PostgreSQL. PDF files live in the Docker named volume
`personal_study_lecture_uploads`, mounted at `/data/lecture_uploads` in the
backend. Both the database and lecture PDFs survive ordinary
`docker compose down` / `docker compose up -d` cycles. Removing volumes will
delete them.

Subject pages list their saved lecture materials. A lecture page shows its page
count, linked question/section counts, and an **Open PDF** action. Question and
review screens link to `/api/lecture-sources/{id}/file`; numeric source pages are
also passed to compatible browser PDF viewers using `#page=N`.

## Generate concise notes

Open **Notes** to generate compact formula, theorem, concept, and procedure
references from either a saved lecture or a new PDF. Note generation uses the
same subject profiles and model selector as question generation, but has its own
base prompt and output schema. The preview must be approved before notes are
saved. Re-uploaded PDFs retain the existing SHA-256 reuse behavior.

Saved notes are available from their subject and section pages. Notes support
Markdown, LaTeX, source-page links, editing, and deletion. They are stored in a
separate `notes` table and never create questions, review history, or FSRS state.
Saving a note with the same normalized source document, type, and title skips it
as a duplicate instead of overwriting the existing note.

Note endpoints:

```text
POST   /api/notes/generation
POST   /api/notes
GET    /api/subjects/{subject_id}/notes
GET    /api/sections/{section_id}/notes
PATCH  /api/notes/{note_id}
DELETE /api/notes/{note_id}
```

Stop the application without deleting study data:

```bash
docker compose down
```

PostgreSQL data is stored in the named Docker volume
`personal_study_postgres_data`. Do not add `--volumes` to `docker compose down`
unless you intentionally want to erase the database.

## Use it from a phone

Connect the phone to the same local network as the laptop, find the laptop's
local IPv4 address, and open:

```text
http://LAPTOP_LOCAL_IP:3000
```

For example: `http://192.168.1.42:3000`. Port 3000 is bound to all network
interfaces. Your operating-system firewall may ask you to allow incoming local
connections.

## Backend tests

The test suite uses a temporary SQLite database and does not touch PostgreSQL:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
```
