# FitFindr

> ### 👋 Start here
>
> **New to this repo? Read [RUNNING.md](RUNNING.md) first** — setup, every
> command, and what to do when something breaks.
>
> Once `python test.py` passes:
>
> ```bash
> python app.py listings --full -n 6      # read the data (Milestone 1)
> python app.py fields                    # what you can filter on
> python app.py ask 'vintage graphic tee under $30'
> ```
>
> All three tools are stubs, so that last command will do nothing useful yet.
> That's the starting position.
>
> **The rest of this file is your submission.** Fill it in as you go.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     HOW TO USE THIS FILE

     This is your submission. Fill each section in as you finish the milestone
     it belongs to — don't leave it all to the end.

     Unit 3 asks for the first five sections. Unit 4 adds the five below them.
     Leave the unit 4 sections alone until then; they're here so you know
     what's coming.

     Everything is pasted as TEXT. No screenshots, no images, no video links.
     A typed block of output gets full credit; a picture of the same output
     gets none.
     ───────────────────────────────────────────────────────────────────────── -->

<!-- ═══════════════════════ UNIT 3 — THE BUILD ═══════════════════════ -->

## What This Does

<!-- Three or four sentences: what a user asks for, and what they get back. -->



---

## Tool Inventory

<!-- Four lines per tool. This is worth 2 points and it's the single most
     common place students lose them.

     "Returns a list" earns NOTHING. The description has to say what is IN
     the list.

     The empty case isn't optional either — it's the thing your loop branches
     on, and if you don't decide it here you'll discover it as a crash in
     Milestone 5. -->

### `search_listings`

- **What it does:** Searches `data/listings.json` for items whose text matches the description's keywords, filtered by size and a price ceiling.
- **Inputs:** `description` (str) — keywords like "vintage graphic tee"; `size` (str or None) — None skips size filtering; `max_price` (float or None) — inclusive ceiling, None skips price filtering.
- **Returns:** A list of up to 10 listing dicts, best keyword match first. Each dict has `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Size matching: the listing's size is split on `/`, spaces and parentheses, and the query size must equal one of those pieces, case-insensitive — so `M` matches `M` and `S/M`, but `S` does not match `US 9` and `L` does not match `XL`.
- **When it has nothing:** An empty list `[]` — never None, never an exception.

### `suggest_outfit`

- **What it does:** Asks the model for one or two outfits built around the new item, using pieces from the user's wardrobe.
- **Inputs:** `new_item` (dict) — one listing dict from `search_listings`; `wardrobe` (dict) — has an `items` key holding a list of wardrobe item dicts, which may be empty.
- **Returns:** A non-empty string of outfit suggestions that name specific wardrobe pieces by name.
- **When it has nothing:** If `wardrobe["items"]` is empty, it returns general styling advice for the item (still a non-empty string) instead of failing.

### `create_fit_card`

- **What it does:** Asks the model to write a short social-media caption about the find and the outfit.
- **Inputs:** `outfit` (str) — the string from `suggest_outfit`; `new_item` (dict) — the same listing dict.
- **Returns:** A 2–4 sentence caption string that mentions the item, its price and its platform once each.
- **When it has nothing:** If `outfit` is empty or only whitespace, it returns the string `"No outfit to write a fit card for."` without calling the model.

---

## Planning Loop

<!-- Your branch rule, stated as a rule — the condition AND both paths — plus
     the file and function that holds it.

     Like this:
       "If search_listings returns an empty list, put a message in the session
        and stop. Otherwise take the first result and go to suggest_outfit."
        — agent.py::run_agent

     The grader checks your code against what you claim here, so the file and
     function have to be real. -->

**Branch rule:** If `search_listings` returns an empty list, put a message in `session["error"]` that says which filter ruled everything out and what to change, then stop — `suggest_outfit` is never called. Otherwise take the first result as `session["selected_item"]` and go to `suggest_outfit`, then `create_fit_card`.

**Where it lives:** `agent.py::run_agent`

**How the query is parsed:** Regex, in `agent.py::parse_query`. `$30` (with or without "under") becomes `max_price`; `size M` or a standalone size like `M`/`XL` becomes `size`; whatever words are left become the `description`.

**What moves through the session:** `query` → `parsed` (description, size, max_price) → `search_results` → `selected_item` (first result) → `outfit_suggestion` → `fit_card`. Each tool reads its inputs from the session, not from the previous call's return value. On the empty path, `error` is set and `selected_item`, `outfit_suggestion` and `fit_card` stay None.

---

## Sample Run

<!-- Two things go here.

     1. One FULL query and its output, pasted as text.
     2. Your three per-tool terminal tests — the command and what it printed. -->

**One full query**

```
$ python app.py ask 'vintage graphic tee under $30'

  Found:    Y2K Baby Tee — Butterfly Print — $18.0 on depop

  Outfit:   Outfit One:
Pair the butterfly baby tee with your baggy dark-wash straight-leg jeans, black combat boots, and the black crossbody bag. Layer the vintage black denim jacket on top for a classic Y2K street style look.

Outfit Two:
Wear the baby tee with your wide-leg khaki trousers, brown leather belt, and chunky white sneakers. Layer your black cropped zip hoodie open over the tee for a casual, balanced contrast of fitted and baggy silhouettes.

  Fit card: Just scored the absolute cutest Y2K butterfly baby tee on depop for only $18, and I’m obsessed with the nostalgic early 2000s energy. I’ve been styling it with baggy dark-wash denim and combat boots for an edgy street style look, or balancing the fitted silhouette with wide-leg trousers and chunky sneakers. It's in amazing condition and brings all the best effortless butterfly-era vibes.

0 model calls this session, 2 served from cache
```

**An impossible query (the branch)**

```
$ python app.py ask 'designer ballgown size XXS under $5'

  Nothing matched "designer ballgown" in size XXS under $5. No listing mentions those words at all — try a broader item type like "tee", "jeans" or "jacket".

0 model calls this session
```

**The three tools, tested one at a time**

```
$ python -c "from tools import search_listings; print([(r['id'], r['title'], r['size'], r['price']) for r in search_listings('graphic tee', max_price=30)])"
[('lst_002', 'Y2K Baby Tee — Butterfly Print', 'S/M', 18.0), ('lst_006', 'Graphic Tee — 2003 Tour Bootleg Style', 'L', 24.0), ('lst_017', 'Mesh Long-Sleeve Top — Black', 'S/M', 15.0), ('lst_033', 'Vintage Band Tee — Faded Grey', 'L', 19.0), ('lst_011', 'Low-Rise Cargo Pants — Khaki', 'W29', 27.0), ('lst_012', 'Oversized Crewneck Sweatshirt — Vintage Navy', 'XL (fits oversized)', 20.0), ('lst_015', 'Vintage Graphic Hoodie — Faded Black', 'L', 26.0)]

```

```
$ python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_example_wardrobe()))"
Outfit 1:
Pair the Levi's 501 jeans with the white ribbed tank top, the vintage black denim jacket, and the chunky white sneakers. Add the black crossbody bag to complete the casual, retro-casual look. 

Outfit 2:
Pair the jeans with the oversized grey crewneck sweatshirt layered over the white ribbed tank top, the black combat boots, and the brown leather belt. Finished with the black crossbody bag for a grunge-inspired everyday fit.

```

```
$ python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0]))"
Scored these vintage Levi's 501s on Depop for just $38 and I'm obsessed with the natural knee fading. They give off such an effortless, lived-in 90s vibe. Just threw them on with my favorite white sneakers for the ultimate casual weekend fit.

```

---

## How I Used AI

<!-- Two specific moments. What you asked, what came back, what you changed.

     "I used Claude to help me code" is not enough.

     "I gave Claude my search_listings spec. It returned None on no match
     instead of an empty list, so I changed it" is the level we want. -->

**Moment 1**

- *What I asked for:*
- *What came back:*
- *What I changed:*

**Moment 2**

- *What I asked for:*
- *What came back:*
- *What I changed:*

<!-- ═══════════════════════ UNIT 4 — THE TEST ═══════════════════════

     Don't fill these in during unit 3.
     ═══════════════════════════════════════════════════════════════════ -->

---

## Run Log — Before

<!-- Five criteria, five tries each, in this exact format.

     Five, because your criteria are written out of five. Mark each try PASS
     or FAIL, count the passes, and read that count against your target — a
     row targeting 4 of 5 with three PASS cells is MISSED (3/5).

     `python run_eval.py --label before` runs everything and writes the table
     into results/. Paste it here and fill in the verdicts. -->

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Real output from one try**, pasted as text, naming the file and function
that produced it:

```

```

---

## Verdicts and Diagnoses

<!-- MET or MISSED per criterion against LAST UNIT's target, plus a sentence on
     how you decided.

     Then, for every miss: which of the four places it happened — a tool, the
     loop's branch, the session, or the model's output — AND the mechanism.

     Not a diagnosis:  "The fit card was bad."
     A diagnosis:      "The fit card criterion missed on 2 of 5 items. Both had
                        an empty brand field. My prompt puts the brand in the
                        first sentence, so the card opened with a blank and read
                        like a fragment. The tool worked; the prompt assumed a
                        field that isn't always there."

     Look for a pattern. Three misses on the same tool is one problem, not
     three. -->

| # | Criterion | Target | Verdict | How I decided |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

**Diagnoses**



---

## Loop Trace

<!-- One full run, printed step by step, with the MCP call visible in it.

     `python app.py ask '...' --trace` once you've added the trace.step()
     calls in Milestone 2.

     Worth pasting BOTH the happy path and the empty-search path. The empty
     one should be visibly shorter, because it stops. If your two traces are
     the same length, your branch isn't working — and this is the fastest way
     anyone will ever find that out. -->

**Happy path**

```

```

**Empty search**

```

```

**On the MCP move:** <!-- what changed in your code, and whether anything
behaved differently afterwards. If the rewire didn't work, say exactly where it
broke — the error text and the last thing that worked. That earns the point in
full. -->



---

## The Improvement

<!-- What you changed, why your diagnosis pointed at it, and the after-run in
     the same table format. One change, measured properly.

     `python run_eval.py --label after` -->

**What I changed:**

**Which failure it was meant to fix:**

### Run Log — After

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Did it help, and how do I know:**

<!-- If it made things worse, say that. Honestly reported, that earns full
     credit and is more interesting than one that worked. -->



---

## What's Still Broken

<!-- For each criterion still missed: what you'd do, and why you stopped where
     you did. "I ran out of time" is fine if it's true. Pretending nothing is
     left is not. -->



<!-- ═════════════════════════════════════════════════════════════════════

     SUBMISSION CHECKLIST — unit 3

       [ ] criteria.md has five numbered criteria, each with a target
       [ ] Each criterion has a reason underneath it
       [ ] All five unit 3 sections above have real content
       [ ] Tool Inventory: all three tools, inputs WITH TYPES, a specific
           return value, and the empty case
       [ ] Planning Loop names the branch rule and agent.py::run_agent
       [ ] Sample Run: one full query plus the three per-tool tests, as text
       [ ] At least four new commits
       [ ] Repository URL submitted — WRITE IT DOWN, you submit the same one
           next unit

     SUBMISSION CHECKLIST — unit 4

       [ ] mcp_server.py exists with one tool registered
           (or a written record of exactly where the rewire broke)
       [ ] Run Log — Before, five criteria, five tries each
       [ ] Real output pasted underneath, naming file and function
       [ ] A verdict on every criterion
       [ ] A diagnosis for every miss, naming a place AND a mechanism
       [ ] Loop Trace, with the MCP call visible in it
       [ ] All three failure modes triggered and handled
       [ ] One improvement, with Run Log — After in the same format
       [ ] What's Still Broken
       [ ] At least four new commits
       [ ] The SAME repository URL as last unit

     Do not delete and recreate this repository. Your commit history is what
     shows your criteria existed before your results did.
     ═════════════════════════════════════════════════════════════════════ -->

---

📖 **How to run this project: [RUNNING.md](RUNNING.md)**
