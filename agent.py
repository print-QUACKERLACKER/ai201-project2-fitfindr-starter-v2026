"""
The FitFindr planning loop.

This is the file that makes FitFindr an agent rather than a script. It decides
which tool to run next based on what the last one returned.

If your loop calls all three tools no matter what comes back, you have a list
of function calls. A loop looks at the last result before it picks the next
step. **That branch is the graded part of this unit.**

Build and test your three tools in `tools.py` first. Then come here.

    python agent.py          runs both example paths below
"""

import re

import config
import trace
from tools import search_listings, suggest_outfit, create_fit_card
from generate import ModelUnavailable


# ── session state ─────────────────────────────────────────────────────────────

def new_session(query: str, wardrobe: dict) -> dict:
    """
    A fresh session for one user interaction.

    The session is the single source of truth for a run. Every tool result goes
    in here, and the next tool reads it back out.

    You could pass values straight from one call to the next. It would work,
    and you would not be able to test it — you can't print a variable you have
    already overwritten. Going through the session is what makes the state
    visible, and unit 4 has you write a criterion about exactly that.

    Add fields if you need them.
    """
    return {
        "query": query,              # what the user typed
        "parsed": {},                # description / size / max_price you pulled out of it
        "search_results": [],        # everything search_listings returned
        "selected_item": None,       # the one you chose — goes into suggest_outfit
        "wardrobe": wardrobe,        # the user's wardrobe
        "outfit_suggestion": None,   # what suggest_outfit returned
        "fit_card": None,            # what create_fit_card returned
        "error": None,               # set when the run ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the loop once and return the finished session.

    Args:
        query:    what the user asked for, in plain language
                  (e.g. "vintage graphic tee under $30, size M").
        wardrobe: a wardrobe dict — get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py.

    Returns:
        The session dict. **Check session["error"] first** — if it isn't None,
        the run ended early and the later fields will still be None.

    ─────────────────────────────────────────────────────────────────────────
    TODO — build this, following the branch rule you wrote in Milestone 2.

      1. Start a session with new_session().

      2. Count the times round the loop, and call trace.check_iterations(count)
         on each one before you go again. It raises when the count passes
         MAX_ITERATIONS in config.py — see trace.py.

      3. Parse the query into a description, a size, and a max_price. Regex,
         string splitting, or asking the model are all fine — say which you
         chose in your README. Put the result in session["parsed"].

      4. Call search_listings() with what you parsed.
         Put the results in session["search_results"].

         ⚠️ THIS IS THE BRANCH. If nothing came back:
              - put a message in session["error"] saying what the user could
                change — "No results" is not that message
              - return the session
              - do NOT call suggest_outfit with nothing

      5. Choose an item — the first result is fine. Put it in
         session["selected_item"].

      6. Call suggest_outfit() with the selected item and the wardrobe.
         Put the result in session["outfit_suggestion"].

      7. Call create_fit_card() with the outfit and the item.
         Put the result in session["fit_card"].

      8. Return the session.

    ─────────────────────────────────────────────────────────────────────────
    IN UNIT 4 you come back and add two things:

      • Trace calls. One per step. `trace.step("search_listings", inputs=...,
        returned=...)` — see trace.py. Your README needs the output.

      • A handler for ModelUnavailable, so a bad key produces a message rather
        than a stack trace. The import is already at the top of this file.
    """
    session = new_session(query, wardrobe)
    session["parsed"] = parse_query(query)

    step = "search"
    count = 0
    while step != "done":
        count += 1
        trace.check_iterations(count)

        if step == "search":
            parsed = session["parsed"]
            session["search_results"] = search_listings(
                parsed["description"], parsed["size"], parsed["max_price"]
            )
            # The branch: nothing found means stop here, before suggest_outfit.
            if not session["search_results"]:
                session["error"] = _no_results_message(parsed)
                step = "done"
            else:
                session["selected_item"] = session["search_results"][0]
                step = "suggest"

        elif step == "suggest":
            session["outfit_suggestion"] = suggest_outfit(
                session["selected_item"], session["wardrobe"]
            )
            step = "card"

        elif step == "card":
            session["fit_card"] = create_fit_card(
                session["outfit_suggestion"], session["selected_item"]
            )
            step = "done"

    return session


# ── query parsing ─────────────────────────────────────────────────────────────

# Sizes as they appear in the data. "size M" is always read as a size; a bare
# letter only counts when it stands alone, so the "a" in "a tee" isn't a size.
_SIZE_WORDS = r"XXS|XS|S|M|L|XL|XXL"


def parse_query(query: str) -> dict:
    """
    Pull a description, a size and a max_price out of a plain-language query,
    with regex. "vintage graphic tee under $30, size M" becomes
    {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}.
    """
    text = query

    max_price = None
    price = re.search(r"(?:under|below|less than|max|up to)?\s*\$\s*(\d+(?:\.\d+)?)", text, re.I)
    if price:
        max_price = float(price.group(1))
        text = text[: price.start()] + " " + text[price.end():]

    size = None
    sized = re.search(r"\bsize\s+([A-Za-z0-9.]+)", text, re.I) or re.search(
        rf"\b({_SIZE_WORDS})\b", text
    )
    if sized:
        size = sized.group(1).upper()
        text = text[: sized.start()] + " " + text[sized.end():]

    text = re.sub(r"\b(looking for|i want|i need|find me|show me)\b", " ", text, flags=re.I)
    description = " ".join(re.sub(r"[,.!?]", " ", text).split())

    return {"description": description, "size": size, "max_price": max_price}


def _no_results_message(parsed: dict) -> str:
    """
    Say why the search came back empty and what to change. Re-runs the search
    with each filter removed to find out which one ruled everything out.
    """
    desc, size, max_price = parsed["description"], parsed["size"], parsed["max_price"]
    looked_for = f'"{desc}"'
    if size:
        looked_for += f" in size {size}"
    if max_price is not None:
        looked_for += f" under ${max_price:g}"

    if not search_listings(desc):
        return (
            f"Nothing matched {looked_for}. No listing mentions those words at all — "
            f"try a broader item type like \"tee\", \"jeans\" or \"jacket\"."
        )

    tips = []
    if max_price is not None and search_listings(desc, size, None):
        cheapest = min(l["price"] for l in search_listings(desc, size, None))
        tips.append(f"raise your max price — the cheapest match is ${cheapest:g}")
    if size and search_listings(desc, None, max_price):
        tips.append(f"drop the size {size} filter")
    if not tips:
        tips.append("loosen both the size and the price")

    return f"Nothing matched {looked_for}. Try: " + "; or ".join(tips) + "."


# ── running it directly ───────────────────────────────────────────────────────

def _show(session: dict) -> None:
    if session["error"]:
        print(f"  stopped: {session['error']}")
        print(f"  fit_card is {session['fit_card']!r} — it should still be None here")
        return

    item = session["selected_item"] or {}
    print(f"  found:    {item.get('title')} — ${item.get('price')} on {item.get('platform')}")
    print(f"  outfit:   {session['outfit_suggestion']}")
    print(f"  fit card: {session['fit_card']}")


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== A query the data can match ===")
    _show(run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    ))

    print("\n=== A query it can't ===")
    _show(run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    ))

    print(
        "\nThe second one should stop before the fit card. If both paths look "
        "the same,\nthe branch isn't doing anything yet."
    )
