# Deploying SaafSaans

The app needs Python and, to show live air quality, one free WAQI token. Nothing else
is required: with no Elasticsearch it falls back to in-process advisory retrieval, and
with no model key it answers from deterministic rules. Both fallbacks are visible in the
UI rather than disguised, so a deployment without them is honest rather than broken.

**No deployment has been executed.** Pushing to a host needs an account this repository
does not have. What *has* been verified is the container itself — see
[Verified locally](#verified-locally) for what was actually run and what came back.
Platform terms were read on 2026-07-20 and are quoted with their sources in
[the platform comparison](#what-the-platforms-actually-offer-july-2026); they change often
enough that you should re-read the pricing page before relying on any figure here.

## What you need first

1. A free WAQI API token: <https://aqicn.org/data-platform/token/>.
   WAQI's terms are non-commercial — no resale, no paid application, no redistributing
   cached or archived data. Fine for a public demo; a commercial deployment would need
   OpenAQ or a direct CPCB agreement.
2. Optionally an OpenRouter key. Leave it unset and every answer comes from the
   rule-based path, which is the honest default for a public demo: a visitor exercises
   the deterministic behaviour, and the Observability view reports the fallback rate
   rather than hiding it.

## Correction, 20 July 2026: Hugging Face Docker Spaces are not free

This document previously recommended Hugging Face Spaces on the grounds that it was the
only genuinely $0 option. **That was wrong, and it was found by trying it rather than by
reading harder.** Creating the Space returned:

```
Error: Client error '402 Payment Required' for url 'https://huggingface.co/api/repos/create'
Static Spaces are free for everyone, but hosting Gradio and Docker Spaces on free
cpu-basic requires a PRO subscription. Subscribe at https://huggingface.co/pro
```

Hugging Face's own pricing page still lists "Create Gradio & Docker Spaces" under the free
tier, so the marketing page and the API contradict each other. The API is what governs, and
PRO is $9/month — more than Fly.io costs for a better-placed server.

The research behind the original recommendation quoted real documentation pages and was
careful to mark what it could not verify. It still produced a false conclusion, because
every source it read was a *description* of the platform rather than the platform. This is
the same failure this repository was written to document, one level up: a claim that
survived review because nobody executed it. **A platform's terms are not verified until you
have tried to use them.**

## Recommended: Fly.io, Mumbai

The honest first choice once cost is equalised. It has a region in India, which no free
option does, and scale-to-zero means an idle demo costs approximately nothing.

1. `flyctl launch --no-deploy --name saafsaans --region bom` — writes `fly.toml`.
2. Put this at the very top of the Space's `README.md`, before anything else:

   ```yaml
   ---
   title: SaafSaans
   emoji: "\U0001FAE7"
   colorFrom: blue
   colorTo: gray
   sdk: docker
   app_port: 7860
   ---
   ```

3. Settings → **Variables and secrets** → New secret:
   `WAQI_TOKEN` = your token. Add `OPENROUTER_API_KEY` only if you want model answers.
   Secrets arrive as environment variables; nothing is baked into the image.
4. Push:

   ```bash
   git remote add space https://huggingface.co/spaces/<user>/saafsaans
   git push space HEAD:main
   ```

5. Check it: `curl https://<user>-saafsaans.hf.space/health` should return
   `{"ok":true,"es":"none","waqi":true,"llm":false}`. `es":"none"` is expected and correct.

### Verified locally

Run on 2026-07-20 with Docker 29.6.1, against the committed `Dockerfile`:

```bash
docker build -t saafsaans .
docker run -d -p 7860:7860 -e WAQI_TOKEN=... saafsaans
curl localhost:7860/health
```

What came back:

- The image builds clean and is **309 MB**.
- `id` inside the container returns `uid=1000(app) gid=1000(app)` — non-root, and the UID
  Hugging Face Spaces requires.
- `/health` returns `{"ok":true,"es":"none","waqi":true,"llm":false}` with a token set, and
  `"waqi":false` without one. `"es":"none"` is the app running with no Elasticsearch at all,
  which is the deployment target.
- `/`, `/guide`, `/city` and `/system` all return 200 in both cases.
- With a token, the Today page renders live Delhi data and the WHO comparison line.
- `docker inspect` reports the container `healthy` after the start period, so the
  `HEALTHCHECK` works rather than merely being present.

What this does **not** verify: anything about a hosting provider. The Space config, the
secret handling and the platform terms below are read from documentation and have not been
exercised against a real account.

## What the platforms actually offer (July 2026)

Read on 2026-07-20. Quotes are from the linked page.

| Platform | Free? | Sleeps | India region |
|---|---|---|---|
| **Hugging Face Spaces** | Yes, CPU Basic | after **48 h** idle | no |
| Fly.io | no — legacy plans only | scale-to-zero, opt-in | **yes** (`bom`) |
| Render | yes, 750 h/mo | after **15 min** idle | not verified |
| Railway | no — $5/mo floor | — | — |
| PythonAnywhere | yes, but ASGI is experimental | — | — |

- **Hugging Face** — "CPU Basic | 2 vCPU | 16 GB | - | 50 GB | Free!"
  ([spaces-gpus](https://huggingface.co/docs/hub/en/spaces-gpus)); "it will go to sleep if
  inactive for more than a set time (currently, 48 hours)" (same page). FastAPI is an
  advertised use of the Docker SDK, and `app_port` overrides the default 7860
  ([spaces-sdks-docker](https://huggingface.co/docs/hub/spaces-sdks-docker)). Outbound
  traffic is limited to ports 80, 443 and 8080, which covers the WAQI API over HTTPS
  ([spaces-overview](https://huggingface.co/docs/hub/spaces-overview)). No region is
  documented; expect a couple of hundred milliseconds extra from Delhi.
- **Fly.io** — the free allowance is legacy: those resources "are still honored for any
  organizations that were on these plans before we sunset them"
  ([pricing](https://fly.io/docs/about/pricing/)). A new account pays. The smallest machine,
  `shared-cpu-1x` 256 MB, is listed at **$2.02/month** on the Amsterdam row; the page notes
  prices vary by region and I could not find a Mumbai figure. A card or a $25 prepaid credit
  is required ([billing](https://fly.io/docs/about/billing/)). It has a Mumbai region, `bom`
  ([regions](https://fly.io/docs/reference/regions/)), and opt-in scale-to-zero
  ([autostop](https://fly.io/docs/launch/autostop-autostart/)).
- **Render** — "Render spins down a Free web service that goes 15 minutes without receiving
  any inbound traffic" and "This process takes about one minute"
  ([free](https://render.com/docs/free)). A documented one-minute cold start after a quarter
  of an hour of quiet is the wrong shape for a link someone taps once.
- **Railway** — "The Hobby Plan is $5 a month" ([plans](https://docs.railway.com/pricing/plans));
  the trial is "a one-time grant of $5 in credits… expire in 30 days"
  ([free-trial](https://docs.railway.com/pricing/free-trial)).
- **PythonAnywhere** — the free tier does allow the WAQI host: both `waqi.info` and
  `api.waqi.info` are on the [allowlist](https://www.pythonanywhere.com/whitelist/). But ASGI
  hosting is explicitly unsettled — "We have not worked out the long-term pricing for ASGI
  sites" — and there is "no support for static file mappings"
  ([ASGI](https://help.pythonanywhere.com/pages/ASGICommandLine/)), which this app needs.
- **Google Cloud Run** has a real free tier — "2 million requests per month… 180,000 vCPU-seconds"
  ([free tier](https://docs.cloud.google.com/free/docs/free-cloud-features)) — but requires a
  billing account, and whether `asia-south1` qualifies for it is **not stated on that page and
  was not verified**.
- **Oracle Cloud Always Free** was not evaluated: <https://www.oracle.com/cloud/free/> returned
  HTTP 403. No claim is made about it either way.

## If you outgrow the free tier

Fly.io with the same Dockerfile is the upgrade with the clearest benefit for this audience:
`primary_region = "bom"` puts the server in Mumbai, and leaving autostop off removes the cold
start. Roughly $2/month at the smallest size. That is the only reason to pay here — the app
itself needs almost nothing.

## Environment variables

| Variable | Required | Effect when unset |
|---|---|---|
| `WAQI_TOKEN` | for live data | every reading is a labelled cached sample; the UI says so |
| `PORT` | no | defaults to 7860 |
| `OPENROUTER_API_KEY` | no | answers come from the rule-based path, logged as fallbacks |
| `ELASTIC_URL` (or `ELASTIC_CLOUD_ID`) + `ELASTIC_API_KEY` | no | System views show their designed empty states |
