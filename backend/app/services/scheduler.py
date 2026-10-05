from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Question, ReviewHistory, ReviewState
from app.schemas import RateResponse, RatingName


RATINGS: dict[RatingName, Rating] = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}


def rate_question(
    db: Session,
    question_id: int,
    rating_name: RatingName,
    reviewed_at: datetime | None = None,
) -> RateResponse | None:
    state = db.scalar(
        select(ReviewState)
        .where(ReviewState.question_id == question_id)
        .with_for_update()
    )
    if state is None:
        return None

    now = reviewed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    card = Card.from_json(state.card_json)
    before_json = card.to_json()
    previous_due = state.due_at
    previous_review = card.last_review

    updated_card, _ = Scheduler().review_card(
        card, RATINGS[rating_name], review_datetime=now
    )

    state.due_at = updated_card.due
    state.state = updated_card.state.name.lower()
    state.stability = updated_card.stability
    state.fsrs_difficulty = updated_card.difficulty
    state.scheduled_days = max(0, (updated_card.due - now).days)
    state.elapsed_days = (
        max(0, (now - previous_review).days) if previous_review is not None else 0
    )
    state.reps += 1
    if rating_name == "again":
        state.lapses += 1
    state.last_review_at = now
    state.card_json = updated_card.to_json()

    history = ReviewHistory(
        question_id=question_id,
        rating=rating_name,
        reviewed_at=now,
        previous_due_at=previous_due,
        next_due_at=updated_card.due,
        review_state_before=before_json,
        review_state_after=updated_card.to_json(),
    )
    db.add(history)
    db.commit()

    return RateResponse(
        question_id=question_id,
        rating=rating_name,
        reviewed_at=now,
        next_due_at=updated_card.due,
        state=state.state,
    )

