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
