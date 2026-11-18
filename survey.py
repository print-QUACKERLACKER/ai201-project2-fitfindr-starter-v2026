"""
The style survey — the capstone extension (shape C).

A user answers up to three fixed questions. Instead of always taking the first
search result, the agent picks the result that best matches those answers.

    GET  /survey                    the questions and their allowed answers
    POST /ask  {"query": "...",
                "survey": {"style": "streetwear", "colors": "dark",
                           "condition": "like_new"}}

Every question is optional; leave `survey` out entirely and the agent behaves
exactly as it did before the extension (first result wins).

Scoring is plain rules over fields the listings already have — style_tags,
colors, condition — with no model call. That keeps the extension free (it adds
zero tokens to a run) and makes the pick the same every time for the same
answers and the same search results, which is what makes it testable.
"""

# Each answer maps to the listing values that count as a match.
QUESTIONS = {
    "style": {
        "question": "Which style sounds most like you?",
        "answers": {
            "streetwear": {"streetwear", "athletic", "graphic tee", "oversized", "baggy", "cargo"},
            "vintage": {"vintage", "70s", "90s", "classic"},
            "cottagecore": {"cottagecore", "floral", "crochet", "feminine", "linen", "boho"},
            "grunge": {"grunge", "band tee", "flannel", "goth", "rock"},
            "y2k": {"y2k", "2000s", "platform", "glam"},
            "minimal": {"minimal", "basics", "classic"},
        },
        "weight": 3,
    },
    "colors": {
        "question": "Which colours do you reach for?",
        "answers": {
            "neutral": {"tan", "cream", "white", "off-white", "ivory", "khaki", "camel",
                        "brown", "beige", "grey", "gray"},
            "dark": {"black", "charcoal", "navy", "burgundy", "wine", "olive", "brown"},
            "bright": {"red", "orange", "pink", "dusty pink", "purple", "teal",
                       "light blue", "rust", "colorful"},
        },
        "weight": 1,
    },
    "condition": {
        "question": "How much wear are you OK with?",
        "answers": {
            "any": {"excellent", "good", "fair"},
            "like_new": {"excellent"},
        },
        "weight": 2,
    },
}


class SurveyError(ValueError):
    """The survey was malformed. The message says what the caller can fix."""


def public_questions() -> dict:
    """What GET /survey shows: the questions and allowed answers, no internals."""
    return {
        key: {"question": q["question"], "answers": sorted(q["answers"])}
        for key, q in QUESTIONS.items()
    }


def validate(survey) -> dict | None:
    """
    Check a survey from a request. Returns a clean dict, or None for "no survey".

    Raises SurveyError naming the bad field and the allowed answers, so the
    server can return a 400 the caller can act on instead of a 500.
    """
    if survey is None:
        return None
    if not isinstance(survey, dict):
        raise SurveyError("'survey' must be an object like "
                          '{"style": "streetwear", "colors": "dark"}.')
    clean = {}
    for key, value in survey.items():
        if key not in QUESTIONS:
            raise SurveyError(f"Unknown survey question '{key}'. "
                              f"Questions are: {', '.join(QUESTIONS)}.")
        if value is None or value == "":
            continue  # skipped question
        answer = value.strip().lower() if isinstance(value, str) else value
        allowed = QUESTIONS[key]["answers"]
        if answer not in allowed:
            raise SurveyError(f"'{value}' isn't an answer to '{key}'. "
                              f"Choose one of: {', '.join(sorted(allowed))}.")
        clean[key] = answer
    return clean or None


def score(listing: dict, survey: dict) -> tuple[int, list[str]]:
    """How well one listing matches the survey, and which answers it matched."""
    total, matched = 0, []
    for key, answer in survey.items():
        q = QUESTIONS[key]
        wanted = q["answers"][answer]
        if key == "style":
            hit = bool(wanted & {t.lower() for t in listing.get("style_tags", [])})
        elif key == "colors":
            hit = bool(wanted & {c.lower() for c in listing.get("colors", [])})
        else:  # condition
            hit = str(listing.get("condition", "")).lower() in wanted
        if hit:
            total += q["weight"]
            matched.append(f"{key}={answer}")
    return total, matched


def pick(results: list[dict], survey: dict | None) -> tuple[int, dict]:
    """
    Choose one search result. Returns (index into results, reason dict).

    No survey → index 0, exactly the pre-extension behaviour. With a survey →
    the highest score; ties go to the earlier result, so search relevance still
    breaks ties and the pick is deterministic.
    """
    if not survey:
        return 0, {"by": "first_result"}
    best_i, best_score, best_matched = 0, -1, []
    for i, listing in enumerate(results):
        s, matched = score(listing, survey)
        if s > best_score:
            best_i, best_score, best_matched = i, s, matched
    max_score = sum(QUESTIONS[k]["weight"] for k in survey)
    return best_i, {
        "by": "survey",
        "position": best_i,
        "score": best_score,
        "max_score": max_score,
        "matched": best_matched,
    }
