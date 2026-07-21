# 0003 — Notifications, and the pull ritual instead

**Status: DECIDED 2026-07-21.** Push stays cancelled. The ritual is a saved URL.

Push notifications are *doubly* blocked: the evidence for them is weak on its own merits,
and the architecture forbids them. Either alone would be enough. The product answer is a
**pull ritual** — the user comes back because they have a saved question, not because we
interrupted them.

## Assumptions

The push proposal assumed:

1. That the binding constraint on protective behaviour is **not knowing** the air is bad,
   so telling someone fixes it.
2. That an alert's effect persists across a season.
3. That more alerts produce more protection, monotonically.

All three are contradicted below.

## Analysis

### 1. The evidence against push is behavioural, and it is specific

The finding that matters is the **day-2 collapse**: response to air-quality alerts drops
sharply after the first day of a multi-day episode. Graff Zivin & Neidell (NBER WP 14209)
identify an **economic** mechanism for this rather than an attentional one — postponing an
outdoor activity for one day is cheap; postponing it for five days is not. People stop
responding because the cost of continued compliance exceeds the perceived benefit, not
because they stopped reading.

This is the crucial detail, and it inverts the usual conclusion. If the cause were
inattention, louder and more frequent alerts would help. Because the cause is cost, **more
alerts on day 3 make things worse**: they burn the channel's credibility on days where
compliance was never going to happen.

The same source reports that **short reprieves reset willingness to respond**. A clean day
in the middle of an episode restores responsiveness to the next alert. That is a design
instruction: an alerting channel's value is concentrated in the *first* bad day after a
gap, and spending it on days 2-5 destroys it.

> **Verification status: SEARCH-LAYER ONLY.** This was not adversarially verified. See
> [`research/2026-07-exposure-evidence.md`](../research/2026-07-exposure-evidence.md),
> which marks it as such. Do not cite it in user-facing prose.

The Delhi schools cluster-RCT (~9,000 students, 2 years) points the same way: the arm that
raised protective behaviour was **education** — comprehension — with positive peer
spillovers, while purifiers were *partly offset by risk compensation*. Same verification
caveat. What moved behaviour was people understanding their situation, not hardware and
not a signal.

### 2. Push is architecturally blocked

The Web Push API requires a registered **service worker**. A service worker is a script,
and registering it requires a script. The app ships zero `<script>` tags
(`README.md:70-72`), pinned by `tests/test_web.py:48`. So push cannot be built without
reversing [0001](0001-zero-javascript.md).

**Order matters here.** The architectural block is *not* the reason push is cancelled — if
it were, the honest thing would be to reopen 0001. Push is cancelled on the evidence. The
block is why the question is not even urgent. Recorded in 0001's "risks accepted" so the
dependency is visible from both ends.

Push is also on the standing list of cancelled features that must not be re-added, along
with the exposure ledger, a forecast "best hours" feature, mask health-benefit claims and
WhatsApp.

### 3. The pull ritual

The design that replaces it, in one line: **a saved URL is a saved question.**

The app's entire state — locality, language, age, conditions, plan, and every disclosure
toggle — rides in the query string, because there is no JavaScript to hold it anywhere
else ([0001](0001-zero-javascript.md), "the constraint produced the design"). A
bookmarked or home-screened URL is therefore not a link to a page. It is a link to
*"is today bad for me, a senior with asthma in ITO who was planning to exercise?"* —
persisted, shareable, and answerable on demand.

Why this is the right shape given the evidence above:

- **The user initiates.** Compliance cost is chosen by the person paying it, so the day-2
  collapse mechanism does not apply — nobody is being asked to comply on a day they have
  already decided is too expensive.
- **Salience is preserved for the days that deserve it.** We are not spending attention on
  days 2-5. When a genuinely worst day arrives, the channel — the user's own habit of
  checking — is intact rather than tuned out.
- **It matches what the schools RCT found worked.** A question the user asked, answered in
  their own terms, is comprehension. A notification is a signal.
- **It is honest about what we know.** We can defend "here is your answer when you ask."
  We cannot defend "we will tell you when it matters," because the evidence that
  telling people changes outcomes is exactly what did not survive.

The one thing the pull ritual genuinely cannot do is reach someone who does not think to
look. That is a real loss and it is accepted, not argued away.

## Data points

| Claim | Source | Verified? |
| --- | --- | --- |
| Day-2 alert collapse has an economic, not attentional, mechanism; short reprieves reset willingness to respond | Graff Zivin & Neidell, NBER WP 14209 | **Search-layer only** |
| Education arm raised protective behaviour with peer spillovers; purifiers partly offset by risk compensation | Delhi schools cluster-RCT, ~9,000 students, 2 years | **Search-layer only** |
| Personal protective measures show no lung-function benefit | 2026 meta-analysis, 27 RCTs; FEV1 SMD 0.04, PEF 0.00, FVC 0.00; low/very-low GRADE | Verified — see research doc |
| Push requires a service worker; a service worker is a script | Web Push API | Architectural |
| The app ships zero scripts | `README.md:70-72`; `tests/test_web.py:48` | Test |
| All state rides in the query string | `README.md:70-72`; every control is a link or form | Code |

## What changed our mind

Two things, and neither was "notifications are annoying".

First, the **mechanism** behind the day-2 collapse. We had previously filed alert fatigue
as an attention problem, which implies a design fix — better copy, better timing,
throttling. An economic mechanism implies no design fix at all: the user is behaving
rationally and we cannot lower their cost of compliance from inside a web page.

Second, the **reprieve-reset** finding turned a negative into a positive constraint. It
says attention is a renewable resource with a refractory period. That reframes the pull
ritual from "the thing we can build given no JS" into "the thing that spends attention at
the only moment it works."

## What we kept

- Push cancelled. It was already on the do-not-re-add list; this document supplies the
  reasoning that was previously missing.
- The query-string state model, unchanged — it is the ritual's whole mechanism.
- Zero JavaScript, unchanged. See [0001](0001-zero-javascript.md); this decision does not
  resolve that one.

## What we are modifying

Nothing in code in this run. This is the reasoning record for a cancellation that had
already been made without one. The follow-on product work it implies — making a saved URL
legible *as* a saved question, so a returning user recognises what they saved — belongs to
[0004](0004-value-proposition.md), where the personal delta is the thing worth returning
for.

## Risks accepted

- **Reach.** A pull ritual cannot reach a person who does not open the page. On a genuinely
  dangerous morning, the people most at risk may be exactly the ones not checking. This is
  the real cost and we are paying it knowingly.
- **We have no retention evidence for the ritual either.** Not notifying is better-evidenced
  than notifying, but "a saved URL becomes a habit" is a hypothesis, not a finding. It is
  currently unmeasured.
- **Two of the three behavioural sources are search-layer only.** They are load-bearing for
  this decision and have not been adversarially verified. If they collapse, the decision
  rests on the architectural block alone, which is a much weaker footing.

## What would falsify it

1. **Adversarial verification refutes Graff Zivin & Neidell's mechanism** — e.g. the day-2
   collapse turns out to be attentional after all. Then alert design becomes tractable and
   push is worth re-costing.
2. **Direct evidence that alerts change outcomes in a Delhi-like setting**, with an effect
   surviving a full winter episode rather than one day. This is the single strongest thing
   that would reopen the question.
3. **Observed usage showing the ritual does not form** — user testing or return-visit data
   showing saved URLs are saved once and never reopened. Then "we can reach them when they
   ask" is false and the reach objection becomes decisive.
4. Conversely, **evidence that returning users check on exactly the wrong days** — routine
   on clean days, absent on severe ones — would show the ritual inverts the salience
   argument that justifies it.

Measuring (3) and (4) requires return-visit data the app does not currently collect and
should not collect casually — the privacy position (locality is logged, persona is not) is
load-bearing and must not be traded for a retention metric. The user test in
`docs/USER-TEST.md` is the honest instrument available today.
