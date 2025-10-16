# Security & Privacy Review

## Summary
- No hard-coded secrets were found; runtime credentials (Discord webhook and The Odds API key) are expected via environment variables.
- Persistent betting history stored in the `/data` volume could leak if the host `./data` directory is committed to the repo.
- The MIT license in the repository names the author directly; confirm you are comfortable sharing that personally identifying detail.
- CI currently auto-builds and publishes Docker images to GHCR on pushes and tags, so any merged changes become publicly distributable artifacts.

## Findings
### Secret configuration handled through environment variables
Both the operator guide and the README document that `DISCORD_WEBHOOK_URL` and `THEODDSAPI` must be supplied at runtime and treated as secrets. Keep these values in repository secrets or local environment variables and avoid committing them. 【F:AGENTS.md†L70-L115】【F:README.md†L66-L115】

### Betting ledger persistence may expose private data
Signals are written to a SQLite database at `/data/bets.sqlite`, and the README instructs operators to mount the repository’s `./data` directory into that location when running locally. Without ignoring that directory, it could be added to version control and reveal historical betting recommendations or bankroll information. The new `.gitignore` entry prevents accidental commits, but continue to treat the `data/` folder as sensitive. 【F:app/core/store.py†L1-L19】【F:README.md†L82-L95】【F:.gitignore†L204-L211】

### License discloses the author’s full name
The bundled MIT license lists “Will Kapcio” as the copyright holder. If you prefer to keep your personal identity private in a public project, consider substituting an organization name or updating the notice. 【F:LICENSE†L1-L21】

### CI publishes Docker images automatically
The `Docker Publish (GHCR)` workflow logs in to GitHub Container Registry and pushes built images for every push to `main` and every semver tag. Ensure no secrets or proprietary assets are baked into the image before making the repository public. 【F:.github/workflows/docker-ghcr.yml†L1-L62】

## Recommendations
- Store Discord and The Odds API credentials only in secure secret stores (e.g., GitHub Actions secrets) and avoid echoing them in logs or documentation.
- Keep the newly ignored `data/` directory out of version control, and periodically purge historical SQLite ledgers if they are no longer needed.
- Decide whether the personal name in the MIT license is acceptable for public visibility; update it if necessary.
- Review Docker image contents and workflow triggers before opening the repository to ensure public artifacts do not include sensitive configuration defaults.
