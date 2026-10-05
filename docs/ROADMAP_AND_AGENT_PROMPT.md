# Development Roadmap

The application will be built in two main milestones rather than many tiny phases.

---

# Milestone 1 — Working Study Application

The goal is to get from zero to an application that can actually be used for studying.

Implement together:

## Infrastructure

- Docker Compose;
- Next.js frontend;
- FastAPI backend;
- PostgreSQL;
- named Docker volume;
- Alembic migrations;
- health checks.

## Data

- Subject;
- Section;
- Question;
- tags;
- ReviewState;
- ReviewHistory;
- ImportBatch.

## Import

- upload JSON;
- validate schema;
- create missing subject;
- create missing section;
- import questions;
- prevent duplicates using `external_id`;
- show import summary.

## Study

- dashboard;
- due-question retrieval;
- question screen;
- Show Answer;
- Again;
- Hard;
- Good;
- Easy;
- FSRS scheduling;
- review history.

## Rendering

- Markdown;
- LaTeX;
- code blocks;
- mobile-responsive review screen.

## Milestone 1 Acceptance Criteria

The following workflow must work:

```text
docker compose up -d --build

        ↓

Open application

        ↓

Upload efes_memories.json

        ↓

Subject appears:
Electronics for Embedded Systems

        ↓

Section appears:
Memory Fundamentals, Organization & Interface

        ↓

Questions appear

        ↓

Start Review

        ↓

Read question

        ↓

Show Answer

        ↓

Press Good

        ↓

FSRS schedules next review

        ↓

ReviewHistory row created

        ↓

docker compose down

        ↓

docker compose up -d

        ↓

All questions and study history still exist
```

The application must also be usable from a phone on the local network.

Do not begin optional polish until this workflow passes.

---

# Milestone 2 — Daily Study Experience

After Milestone 1 works reliably, add:

## Practice Mode

Practice by:

- subject;
- section;
- random questions;
- weak questions;
- configurable question count.

Practice mode must not modify FSRS scheduling.

## Question Management

- edit;
- delete;
- search;
- filter.

## Better Dashboard

Show:

- due today;
- new questions;
- reviewed today;
- subjects;
- due counts per subject.

## Weak Questions

Identify questions with repeated Hard/Again ratings.

## Backup

Add:

```text
scripts/backup.sh
```

and preferably:

```text
scripts/restore.sh
```

## Export

Allow study content to be exported as JSON.

## UI Polish

Improve:

- mobile layout;
- formula display;
- long-answer scrolling;
- code rendering;
- navigation.

---

# Coding Agent Instructions

Before changing code, read:

```text
docs/SPEC.md
docs/TECH_SPEC.md
docs/ROADMAP_AND_AGENT_PROMPT.md
```

Treat these files as the source of truth.

---

# Initial Agent Prompt

You are implementing a personal self-hosted study application.

Read all files under `/docs` before making architectural decisions.

The application is:

- single-user;
- self-hosted on a laptop;
- used from desktop and phone;
- built with Next.js, FastAPI, PostgreSQL and Docker Compose;
- populated using GPT-generated JSON files;
- based on self-graded spaced repetition using Again / Hard / Good / Easy;
- intended primarily for engineering questions containing Markdown, LaTeX, calculations and code.

We are currently implementing **Milestone 1**.

Implement Milestone 1 as one coherent vertical slice.

Do not unnecessarily split the work into many artificial phases.

Do not implement Milestone 2 unless required to make Milestone 1 functional.

Important architectural constraints:

- Keep the architecture simple.
- Do not add Redis.
- Do not add RabbitMQ.
- Do not add Celery.
- Do not add authentication.
- Do not add AI generation.
- Do not add automatic answer grading.
- Use PostgreSQL.
- Use a Docker named volume for persistence.
- Use Alembic for database migrations.
- Use an FSRS-compatible scheduler rather than inventing a scheduling algorithm.
- Imported questions must support Markdown, LaTeX and code.
- The review UI must work well on a phone.
- Importing the same JSON twice must not create duplicate questions.
- Database and review data must survive container recreation.

Development approach:

1. Inspect the repository first.
2. Compare the current implementation against the specifications.
3. Create or adjust the implementation plan internally.
4. Implement Milestone 1 end-to-end.
5. Add meaningful backend tests.
6. Run the tests.
7. Start the Docker stack and verify health where possible.
8. Report exactly what was implemented.
9. Report any remaining Milestone 1 issues.
10. Do not silently change the specification.

The key acceptance workflow is:

```text
JSON import
→ subject/section/questions created
→ start review
→ show answer
→ rate Again/Hard/Good/Easy
→ FSRS updates schedule
→ review history persists
→ restart Docker
→ data still exists
→ review works from mobile browser
```

Prioritize making this complete workflow reliable over adding extra features.