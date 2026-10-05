# Personal Study App — Technical Specification

## 1. Technology Stack

### Frontend

```text
Next.js
TypeScript
React
```

The frontend must be responsive and mobile-friendly.

### Backend

```text
Python
FastAPI
SQLAlchemy
Alembic
```

### Database

```text
PostgreSQL
```

### Infrastructure

```text
Docker
Docker Compose
```

### Scheduling

Use an FSRS-compatible spaced-repetition implementation.

Do not invent a custom scheduling algorithm when a maintained FSRS implementation can be used.

---

# 2. Architecture

```text
Desktop Browser
       │
Phone Browser
       │
       ▼
    Next.js
       │
       │ REST API
       ▼
    FastAPI
       │
       ▼
  PostgreSQL
       │
       ▼
Docker Named Volume
```

The architecture should remain simple.

Do not add Redis, RabbitMQ, Celery or other infrastructure without a real requirement.

---

# 3. Docker Services

Expected services:

```text
frontend
backend
db
```

Example logical structure:

```text
study_frontend
study_backend
study_db
```

PostgreSQL must use a named volume such as:

```text
study_postgres_data
```

---

# 4. Database Model

## Subject

```text
id
name
description
created_at
updated_at
```

Subject name should be unique.

---

## Section

```text
id
subject_id
name
description
created_at
updated_at
```

Relationship:

```text
Subject 1 → N Sections
```

A section name should be unique within its subject.

---

## Question

```text
id
section_id
external_id
question_type
question
answer
difficulty_level
source
source_page
created_at
updated_at
```

`external_id` must be unique.

Supported `question_type` values:

```text
recall
concept
problem
code
```

`difficulty_level` refers to the educational difficulty of the question.

Suggested values:

```text
1 = basic
2 = normal
3 = difficult
```

This must remain separate from FSRS's internal memory difficulty.

---

## QuestionTag

Questions may have multiple tags.

Either use:

```text
Tag
QuestionTag
```

or another clean relational implementation.

Example tags:

```text
memory
addressing
systemc
cache
timing
```

---

## ReviewState

Stores the current spaced-repetition scheduling state for a question.

Fields depend partly on the chosen FSRS implementation but should include sufficient information to restore scheduling exactly.

Conceptually:

```text
question_id
due_at
state
stability
difficulty
scheduled_days
elapsed_days
reps
lapses
last_review_at
```

Do not confuse FSRS difficulty with `Question.difficulty_level`.

---

## ReviewHistory

Every scheduled review must create a permanent history row.

Suggested fields:

```text
id
question_id
rating
reviewed_at
previous_due_at
next_due_at
review_state_before
review_state_after
```

Ratings:

```text
again
hard
good
easy
```

Review history must not be overwritten.

---

## ImportBatch

Store information about imports.

Suggested fields:

```text
id
filename
received_count
imported_count
duplicate_count
error_count
created_at
```

---

# 5. JSON Import Contract

Example complete file:

```json
{
  "schema_version": "1.0",
  "subject": "Electronics for Embedded Systems",
  "section": "Memory Fundamentals, Organization & Interface",
  "source": "efes_memories",
  "questions": [
    {
      "external_id": "efes-memories-001",
      "type": "problem",
      "question": "A digital memory is organized as **4K × 9**. Determine the total size in bits and bytes, the number of address bits, and the valid address range. Then explain why the organization is valid even though 9 is not a power of 2.",
      "answer": "The memory contains:\n\n\\[\nN_{words}=4K=4096=2^{12}\n\\]\n\nand each word has:\n\n\\[\nn_{bits}=9\n\\]\n\nTherefore:\n\n\\[\nSIZE=N_{words}\\times n_{bits}=4096\\times9=36864\\text{ bits}\n\\]\n\nIn bytes:\n\n\\[\n36864/8=4608\\text{ bytes}=4.5\\text{ Kbytes}\n\\]\n\nThe address width is:\n\n\\[\n\\log_2(4096)=12\n\\]\n\nso the valid addresses are 0 through 4095. The number of words must be a power of two, while the word width does not need to be.",
      "difficulty_level": 2,
      "tags": [
        "memory",
        "addressing",
        "capacity"
      ],
      "source_page": null
    }
  ]
}
```

---

# 6. JSON Fields

## Root

Required:

```text
schema_version
subject
section
questions
```

Optional:

```text
source
```

---

## Question

Required:

```text
external_id
type
question
answer
```

Optional:

```text
difficulty_level
tags
source_page
```

Defaults:

```text
difficulty_level = 2
tags = []
source_page = null
```

---

# 7. Import Rules

When importing:

1. Validate the full JSON structure.
2. Validate `schema_version`.
3. Create subject if it does not exist.
4. Create section if it does not exist.
5. Check every `external_id`.
6. Skip existing IDs.
7. Import new questions.
8. Return an import summary.
9. Record the import in `ImportBatch`.

A broken question must not corrupt existing database data.

Prefer transactional imports.

---

# 8. Markdown and Mathematics

Questions and answers must support:

- Markdown;
- fenced code;
- syntax highlighting;
- LaTeX math.

Examples that must render correctly:

```text
**4K × 9**
```

```latex
N_{words}=4096=2^{12}
```

```cpp
SC_MODULE(counter) {
    sc_in<bool> clk;
};
```

Use a safe Markdown rendering strategy.

Do not render arbitrary unsafe HTML from imported content.

---

# 9. Core API

The exact routes may evolve, but the backend should expose functionality equivalent to:

```text
GET    /api/health

GET    /api/subjects
POST   /api/subjects

GET    /api/subjects/{id}
GET    /api/subjects/{id}/sections

GET    /api/sections/{id}
GET    /api/sections/{id}/questions

GET    /api/questions/{id}
PATCH  /api/questions/{id}
DELETE /api/questions/{id}

POST   /api/import

GET    /api/review/due
POST   /api/review/{question_id}/rate

POST   /api/practice/session

GET    /api/dashboard
```

Do not create unnecessary endpoints before they are needed.

---

# 10. Review API Behavior

A due-question endpoint should return enough information to render:

```text
subject
section
question
question type
```

The answer may be returned together with the question because this is a single-user local application, but the frontend must hide it until the user presses `Show Answer`.

Rating endpoint input:

```json
{
  "rating": "good"
}
```

The backend must:

1. load existing FSRS state;
2. apply the selected rating;
3. calculate the new state;
4. update ReviewState;
5. insert ReviewHistory;
6. return the next due date/state.

This operation should be transactional.

---

# 11. Networking

The application runs on the user's laptop.

The frontend must be reachable from another device on the same local network.

The Docker/network configuration must not bind the frontend exclusively to localhost inside the container.

Documentation must explain how to access the application from a phone using:

```text
http://LAPTOP_LOCAL_IP:PORT
```

No public internet exposure is required for V1.

---

# 12. Security

Because this is a local single-user application:

- no authentication is required in V1;
- do not expose PostgreSQL publicly unnecessarily;
- validate imported JSON;
- sanitize rendered Markdown;
- validate API payloads using Pydantic.

---

# 13. Persistence

Database data must live in a Docker named volume.

Application rebuilds must not reset:

- subjects;
- sections;
- questions;
- review states;
- review history;
- imports.

---

# 14. Testing

Backend tests should cover at minimum:

```text
health check
subject creation
section creation
JSON validation
JSON import
duplicate import
question editing
question deletion
due questions
FSRS rating
review history
```

Important integration test:

```text
Import file with 10 questions
→ 10 questions exist

Import same file again
→ 0 new questions
→ 10 duplicates
```

Another important test:

```text
Rate question as Good
→ ReviewHistory created
→ ReviewState updated
→ next due date changes
```

---

# 15. Development Principle

Prefer straightforward code over unnecessary abstractions.

Use service layers where they clarify meaningful logic such as:

```text
importer
scheduler
practice session generation
```

Do not build architecture for hypothetical future requirements.