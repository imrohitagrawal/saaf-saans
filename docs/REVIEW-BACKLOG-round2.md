# RECOVERED — round-2 review findings that were never fixed

Source: workflow run `wf_aab5e103-951` (`saafsaans-cpcb-closeout`), status `completed`.

Recovered 2026-08-09 from `~/.claude/projects/-Users-rohitagrawal-Projects/5bc1d8b6-7681-4a44-b4e3-3fce6710d4ba/workflows/wf_aab5e103-951.json`.
That file is outside the repo and outside git, and the session directory holding it is
temporary. This document is the durable copy.

## Triage as of 2026-08-09

Four independent lenses (architect, tester, security, performance) checked these against the
code. The list is **20 live, not 25**:

- **Already fixed by the run's own round-1 commits** — #17 (held reading pinned 600s, fixed at
  `waqi.py:51-52`), #25 (held payload unreachable on the failing render, `cpcb.py:337-367`),
  plus the empty-200 blanking and the Greater Noida / Ghaziabad wasted fetches.
- **False lead** — #7 (flaky barrier/sleep test) does not reproduce: 30/30 passes under 40-way
  CPU oversubscription, every gate a >=5s timeout against sub-millisecond work. The one
  observed failure is explained by a real network call leaking out of
  `test_guide_matches_behaviour.py:220`, not by barrier timing.
- **Live and reclassified** — #18 is not a testing gap: `waqi.py:462-470` is covered by the
  `[True]` parametrisations and merely unreachable in production because
  `PREFER_TWO_PARTICULATES` ships off.
- **Six (#5, #13, #15, #16, #17, #19)** are reachable only with an Elasticsearch client, which
  production does not have — no `ELASTIC_*` secret exists on the Fly app.

The three `[critical]` held-reading findings are live and are the highest-harm items here: the
Today page prints a band meaning, two risk scores and band advice over a held reading, in
English only, four elements below a hero promising it prints none.

## Why these are outstanding

The run's fix agent for round 2 (`r2:fix`) died on `You've hit your session limit`, so
`result.lastFix` is `null` and **none of the 25 survivors below were applied**.
Rounds 3 and 4 then reported 0 findings because all six review agents in both rounds
died on the same session limit — the loop's convergence test was satisfied by empty
output from dead agents, not by a clean tree.

Round tallies as recorded:

| Round | findings | survived 3-vote refutation | kill rate | fixed? |
|---|---|---|---|---|
| 1 | 35 | 25 | 29% | yes — 7 commits, `e8d5483`..`5e5037a` |
| 2 | 27 | 25 | 7% | **NO — fixer died** |
| 3 | 0 | 0 | 0% | vacuous (agents died) |
| 4 | 0 | 0 | 0% | vacuous (agents died) |

## The 25 unfixed round-2 survivors

Verbatim titles as recorded by the run. Severity is the reviewer's own label.

1. [critical] The held-reading page prints a band word and two risk scores one paragraph after promising it prints neither — both languages
2. [high] English held page prints the Moderate band meaning where Hindi prints "no data" — a band claim the page denies, and a two-language divergence
3. [medium] City Pulse PART legend tells the reader to do something that shows nothing — both languages
4. [medium] The Guide names CPCB and data.gov.in unconditionally while its own footer, on the same page, says no live source is configured
5. [low] The provenance panel says "neither source answered" when neither source was asked
6. [low] The WHO absence line claims what a station is doing "right now" from a reading up to three hours old
7. [low] Flaky concurrency test: barrier/sleep timing, observed failing once in a full-suite run on a clean tree
8. [critical] A held reading still prints two risk scores, a band word and band advice on the Today page — contradicting the hero text and the Guide, in both languages
9. [high] The forwarded share card's og:description is the band advice for a held reading
10. [high] /ask passes the suppressed severity band into the answer card and the LLM system prompt on a held reading
11. [high] The Guide names data.gov.in as the primary source unconditionally, on a deployment that may have no CPCB key — the exact defect the footer branch was added to remove
12. [medium] The WHO line asserts the present tense over a held reading
13. [low] A held reading up to three hours old outranks a possibly-fresher stored Elasticsearch row on City Pulse
14. [high] test_a_held_reading_earns_no_band_word_but_keeps_its_number cannot fail on the hero pill — the guard it names is untested
15. [medium] test_the_footer_reads_the_same_predicates_health_reports is a tautology — green in both directions
16. [medium] The new held_suffix branch in llm._rule_based has no positive assertion — deleting it leaves the suite green
17. [low] test_the_guide_still_names_the_fallback is a bare substring search that survives deleting the fallback claim
18. [low] waqi._choose has an unreachable branch that the suite therefore cannot exercise
19. [low] Mutation results in this working tree are not trustworthy without re-reading the file: two restores were silently reverted
20. [critical] The band meaning takes a different branch in English than in Hindi on a held reading
21. [high] The risk score survives on a held page through the comparison line
22. [high] The footer's source claim was made conditional on configuration; the Guide's identical claim was not
23. [medium] who_line is not freshness-aware, so a held reading still asserts what the air holds
24. [low] The prompt still labels a held reading's line "Live AQI"
25. [high] The held CPCB payload is unreachable on the very render that hits the outage, so /city still blanks a whole city

## Round-1 survivors, for reference — these WERE fixed

1. [critical] The WHO line still says "Right now" over a 24-hour mean — the run's own ADR calls this false and in scope, and a new test now pins it
2. [high] A held reading gets the full band, colour, risk score and advice on Today while City Pulse deliberately denies it all four — same reading, same tag word, two contradictory meanings
3. [medium] Hindi stale_note still blames "the live feed" (singular) after the English was changed to "The feeds" in this same run
4. [medium] prov_none still says "the feed did not answer" in both languages, after the run made two sources
5. [medium] Every page's footer claims "Data: CPCB via data.gov.in, WAQI as fallback" on a deployment where /health reports both false
6. [high] The Guide promises "no band, no colour, no advice" for a held reading; the Today page gives it all three
7. [high] The reading card still says "Right now" after this run's own ADR measured CPCB's number to be a rolling 24-hour mean
8. [medium] The same held reading is rendered two incompatible ways on City Pulse and on Today, and nothing tests the Today side
9. [low] Guide scale_3 says the provenance panel "under any answer" names the source; it names none when source is absent
10. [high] prov_scale_note's PM2.5-only and PM10-only branches can be swapped with the entire suite still green
11. [critical] A held reading earns a band, a colour, a risk score, advice and a "right now" share card on / — while /city denies it a band and the Guide promises it gets none
12. [high] A CPCB payload up to three hours old beats a live WAQI reading that is never requested — and no test pins it either way
13. [high] The Guide was corrected about the averaging window; the sentence it describes was not — who_line still says "Right now" over a 24-hour mean, in both languages
14. [medium] guide.html scale_3 still asserts the number is worked out from PM2.5 and PM10, the exact claim scale_note was split up to stop making
15. [medium] The one-vs-two particulate disclosure landed on / only: /city tiles and the share card carry the index with no such qualification
16. [medium] A held reading reaches the LLM prompt and the answer text with no marker; only `stale` is hedged
17. [high] A held reading is pinned for 600s in waqi's cache, defeating cpcb's 60s failure retry
18. [medium] A successful-but-empty upstream response blanks the city instead of serving the retained payload
19. [medium] Greater Noida and Ghaziabad each cost a full upstream CPCB city fetch that can never match a station
20. [high] The Guide promises no band, no colour and no advice from a held reading; the Today page renders all three
21. [high] The reading card says "Right now" over a quantity this run's own ADR proves is a rolling 24-hour mean
22. [low] A CPCB response that succeeds but is empty is indistinguishable from a failure, and gets served as a held reading on the next render
23. [low] guide scale_3 claims the provenance panel names the source "under any answer"; on a no-reading turn it names neither
24. [low] The five-day outlook and the best-window advice silently disappear on every CPCB-served locality, with no prose explaining it
25. [low] An uncommitted edit to waqi._wants_second_opinion appeared in the working tree during this review

## Machine verdicts

```
averaging: {
  "resolved": true,
  "same_quantity": "different",
  "app_misdescribes_its_numbers": true,
  "summary": "RESOLVED by measurement. CPCB's avg_value on data.gov.in is a rolling 24-hour mean republished hourly; WAQI's iaqi is a US EPA sub-index of the LATEST HOURLY concentration; OpenAQ's measurements are 15-minute instantaneous concentrations. Three different quantities. Method: min_value/max_value fingerprint the window far more sharply than avg_value does \u2014 a 24h minimum is a specific number a shorter or longer window will not reproduce. Against OpenAQ's raw 15-minute series for the same 5 Delhi stations in the same minute (21:00 IST, 21 Jul 2026), CPCB's PM10 minimum matched TO THE UNIT at 4 of 5 stations (RK Puram 27/27.0, NSIT Dwarka 52/52.3, DTU 11/11.0, Anand Vihar 39/39.0) and to 1 ug/m3 at ITO (11/10.0), with means within 4%. WAQI: at 3 stations whose feed name matched OpenAQ's and whose timestamp was the current hour, iaqi inverted through aqi_scale.concentration landed on the latest hourly value 6/6 times; Mandir Marg PM2.5 is decisive (WAQI 1.2, latest hour 1.0, 24h mean 15.6 \u2014 13x apart). This also empirically confirms the EPA inversion that was previously o
honestyBlocks: True
gate:          None   <- the gate agent never ran (session limit)
lastFix:       null   <- no round-2 fix was applied
shipped:       HALTED: the averaging-window research concluded the app misdescribes its numbers (or did not return). Health advice is not shipped on a number we have just learned is mislabelled.
```
