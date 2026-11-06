"""Evidence-based feedback from immutable attempt snapshots; no LLM scoring."""
from uuid import UUID

from app.models.quiz import QuizAttempt
from app.schemas.quiz import (
    AttemptResponse, AttemptSummary, AttemptAnswerResponse,
    ReviewSource, TopicFeedback, QuizFeedback,
)


def review_sources(evidence: list[dict]) -> list[ReviewSource]:
    sources = {}
    for item in evidence:
        try:
            document_id = UUID(str(item["document_id"]))
            page = item["page"]
            if type(page) is not int or page < 1:
                continue
            filename = str(item["filename"])
        except (KeyError, ValueError, TypeError):
            continue
        url = f"/documents/{document_id}/file"
        sources[(document_id, page)] = ReviewSource(
            document_id=document_id, filename=filename, page=page,
            file_url=url, page_url=f"{url}?page={page}",
        )
    return list(sources.values())


def build_attempt_response(attempt: QuizAttempt) -> AttemptResponse:
    answers = []
    groups = {}
    for answer in sorted(attempt.answers, key=lambda item: item.position):
        result = AttemptAnswerResponse.model_validate(answer)
        result.sources = review_sources(answer.evidence)
        answers.append(result)
        label = " ".join(answer.topic.split()) or "General study material"
        group = groups.setdefault(label.casefold(), {"label": label, "answers": []})
        group["answers"].append(result)

    strengths, needs_review = [], []
    for group in groups.values():
        assessed = group["answers"]
        correct = sum(answer.is_correct for answer in assessed)
        wrong = [answer for answer in assessed if not answer.is_correct]
        # Point to the evidence for the missed questions when recommending review.
        focus = wrong or assessed
        unique_sources = {(s.document_id, s.page): s for answer in focus for s in answer.sources}
        message = (
            f"You answered all {len(assessed)} assessed question(s) on this topic correctly. Good work on this attempt."
            if not wrong else
            f"You answered {correct} of {len(assessed)} correctly on this topic. Review the missed question explanations and the linked PDF pages, then try another practice quiz."
        )
        if not unique_sources:
            message = message.replace(" and the linked PDF pages", "")
            message += " PDF page references are unavailable for these saved questions."
        topic = TopicFeedback(
            topic=group["label"], correct=correct, total=len(assessed), feedback=message,
            question_ids=[answer.question_id for answer in focus], sources=list(unique_sources.values()),
        )
        (needs_review if wrong else strengths).append(topic)

    if attempt.score == attempt.total:
        summary = f"Great work: you answered all {attempt.total} questions correctly on this attempt."
    elif attempt.score == 0:
        summary = f"You answered 0 of {attempt.total} correctly this time. Use the explanations and PDF pages below to review one topic at a time."
    else:
        summary = f"You answered {attempt.score} of {attempt.total} correctly. Keep building on what went well and focus your next review on the missed topics below."
    next_steps = [
        f"Review {topic.topic} and read the explanation for each missed question."
        + (" Revisit the linked PDF pages." if topic.sources else " Upload the relevant notes if you need supporting PDF pages.")
        for topic in needs_review
    ]
    next_steps.append(
        "After reviewing, generate a new quiz on the topics you missed."
        if needs_review else
        "Try a new quiz with different questions to check your understanding again."
    )
    return AttemptResponse(
        **AttemptSummary.model_validate(attempt).model_dump(), answers=answers,
        feedback=QuizFeedback(summary=summary, strengths=strengths, needs_review=needs_review, next_steps=next_steps),
    )
