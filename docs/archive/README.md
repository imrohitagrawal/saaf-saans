# Archived branches

Branches deleted from this repository, kept here as patches so nothing is lost
by the deletion.

- `0001-Add-Hugging-Face-Space-configuration-on-a-branch-of-.patch` — the
  `space` branch. It was `v1-closure` plus a fifteen-line Hugging Face Spaces
  YAML header in `README.md`, and nothing else. It was never merged, because
  the header is deployment metadata for one particular host and does not belong
  on `master`; the branch existed so that host could be pointed at it directly.
  SaafSaans deploys to Fly.io instead — see [`../DEPLOY.md`](../DEPLOY.md) — so
  the branch had no remaining purpose.

  Apply with `git am` from the repository root if a Spaces deployment is ever
  wanted again. Note that the patch applies against the tree as it was at
  `4ed3c38`, before the Hindi work merged, so it will need the README hunk
  re-resolving by hand.
