# User test — facilitator script

One page. Print it, or keep it open on a second device. Use
[`user-test-sheet.md`](user-test-sheet.md) — one copy per participant.

**Why this exists.** Section 6 of the case study says every usability claim in this project
is reasoning, not observation. Six agents walked the site in July 2026 and found ten real
problems, but they are heuristic reviewers: they cannot be genuinely ignorant, they have no
stakes, and they do not see a rendered page. This is the part no agent can do.

---

## Before the day

**Who.** Five or six people, **none of whom know about this project**. Anyone who knows you
built it will be kind, and kind data is worthless. Between them you need at least one person
over 60, at least one parent of a school-age child, and at least two who do not work in
technology.

Five is the usual number. It is a rule of thumb rather than a finding — it comes from
Nielsen and Landauer's 1993 model of problem discovery, and it is widely contested. The
honest version: the first two or three people will find the biggest problems, and the rest
tell you whether you were unlucky.

**Where.** In person, on **their** phone, on **their** mobile data. Not your laptop. Half of
what this app is — server-rendered, zero JavaScript, built for a weak signal — only gets
tested on a real device on a real connection. Deploy it first (`docs/DEPLOY.md`), so you can
hand over a link rather than a demo.

**What you must not collect.** Do not write down anyone's name or their real health
condition. If someone volunteers their own asthma or their father's COPD, use it — real
stakes give better data — but record only "used own situation", never what it was. This
project's whole argument is about not holding health data it does not need. That applies to
you, on the day, with a notebook.

**Time.** 20–25 minutes each. Do not run more than three in a row; you stop noticing things.

---

## Opening — say this, roughly in these words

> Thanks for doing this. One thing before we start: I'm testing the website, not you. If
> anything is confusing, that's the website's fault, and that's exactly what I need to find.
> There are no wrong answers here.
>
> I'd like you to think out loud — say what you're looking at, what you expected, what's
> annoying you. If you go quiet I'll nudge you, but I won't help you, because I need to see
> what happens when I'm not sitting here.
>
> I'm not writing down your name or anything about your health.
>
> Any questions?

If you want to record: *"Is it alright if I record the screen and your voice? I'll delete it
once I've written my notes."* If they hesitate at all, don't.

---

## The tasks

### 1. The whole product, in one task

Give the situation, then **stop talking**.

> It's a weekday morning in Delhi. *[Pick one: Your eight-year-old has asthma and walks
> fifteen minutes to school at eight. / You want to walk to the market this afternoon. / You
> want to go for a run this evening.]* You want to know whether that's safe today. Here's
> the link.

Start a timer. Stop it when they say an answer out loud. Write down the words they use.

### 2. Comprehension — after they have answered, not before

Point at the score chip:
> Read that out to me. What does it mean?

Then:
> Is that number about the air, or about you? How can you tell?

Point at the World Health Organization line:
> What's this line telling you?

### 3. Provenance

> Suppose you didn't believe this number. Could you find out where it comes from?

Give them sixty seconds. Note where the trail goes cold.

### 4. Staleness — on City Pulse

Point at one row tagged `CACHED` and one tagged `SAMPLE`:
> What's the difference between these two?

Then:
> Would either of those change what you did today?

### 5. The persona — only if they never found it

> Is there anything on this page that's specific to you?

If yes: *"Could you change it?"* Note how long it takes.

### Closing

> If you had to explain this site to a friend in one sentence, what would you say?
>
> Would you use it again? What would have to be different?

Then stop. Thank them. Do not explain anything you have been biting your tongue about until
after you have written your notes — the temptation to justify the design will contaminate
what you remember.

---

## Prompts that don't lead

Use these, verbatim, when they get stuck. **Count silently to ten first.** The silence is
the instrument; most facilitators break it and destroy the finding.

- "What are you trying to do?"
- "What are you looking at?"
- "What did you expect to happen?"
- "Say a bit more about that."
- "What would you do next if I weren't here?"

**Never say any of these:**

- "Try tapping the…" — you have just answered the question you were measuring.
- "Did you notice the…" — same.
- "That's the risk score, it means…" — you are now testing your explanation, not the page.
- "It's supposed to…" — nobody using it later will have you there to say so.
- "Most people click…" — invented social proof, and it steers.
- "Does that make sense?" — everyone says yes.
- "Do you like it?" — the answer is always yes and it means nothing.

If they ask you a direct question, deflect **once**: *"What do you think?"* If they ask
again, say you'll answer at the end — and write down that they had to ask.

---

## Three things the site will do that you must not explain away

You know why these are the way they are. On the day, they are findings.

- Roughly half the localities show `SAMPLE` rather than a live reading. That is the real
  state of the WAQI feeds. If someone is confused or annoyed, that is data.
- Under `?lang=hi` the persona sentence and the comparison line are still English. Known,
  documented, and still worth watching someone hit.
- The Hindi carries an "unreviewed translation" banner. If a Hindi speaker reads it and
  stops, note it. That is the banner working.

---

## Writing it up

**Within ten minutes of them leaving**, before you rationalise anything. Later is a
different, kinder memory.

- Record what they **did**, not what they said they would do. The two disagree constantly.
- Quote verbatim. Do not tidy the grammar; the hesitation is the signal.
- Any pause over about three seconds is a finding, even if they got there in the end.
- Write down the things that annoyed you about their behaviour. Those are usually the
  findings you are most motivated to discard.

---

## Done

The test is complete when:

1. Five or six sheets are filled in.
2. The findings are written into `docs/CASE-STUDY.md` — **including the ones that make the
   app look bad**, which are the entire point.
3. Section 6's "No real users. Zero people outside the author have used this" is replaced
   with what was observed.
4. Open item 1 in section 9 is closed.

**One honesty check before you call it done.** If all six sessions went smoothly and nobody
was confused by anything, the likely explanations are that you led them, that you recruited
people who wanted to please you, or that you are remembering it generously. A review with a
kill rate near zero is not a review, and the same logic applies here. Six clean sessions
should make you suspicious of the sessions, not confident about the product.
