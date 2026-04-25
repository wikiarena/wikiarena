# WikiArena Deployment

This document describes the current production deployment model for the solver API and graph artifacts. The canonical AWS auth and Terraform runbook lives in [infra/README.md](/Users/hupaulson/projects/wikiarena/infra/README.md).

## Current Production Shape

- Cloudflare fronts `api.wikiarena.org`
- one EC2 instance in `us-west-2` runs the FastAPI solver API behind `nginx`
- immutable graph artifacts live in the graph S3 bucket under dated prefixes
- immutable API bundles live in the deployment S3 bucket under dated prefixes
- the instance reads one graph channel manifest from S3 to decide which graph snapshot is live

## Operational Boundaries

The deployment system is intentionally split into separate concerns:

- `Build Graph`: build and publish immutable dated graph artifacts only
- `Promote Graph`: move one channel manifest, such as `production`, to a chosen dated graph
- `Rollout Graph`: sync the promoted graph onto the host, restart the API, and verify the expected snapshot
- `Deploy API`: ship new application code only and restart against the currently promoted graph

Code deploys and graph rollouts may both restart the service, but they should not be used interchangeably.

## Graph Layout

The graph bucket stores immutable artifacts under dated prefixes:

```text
graphs/enwiki/20260401/wikiarena_graph_enwiki_20260401.bin
graphs/enwiki/20260401/wikiarena_graph_enwiki_20260401.metadata.json
graphs/enwiki/20260401/wikiarena_graph_enwiki_20260401.bin.sha256
```

Production does not discover "latest" by listing S3. Instead it follows a mutable channel manifest:

```text
graphs/enwiki/channels/production.json
```

That manifest points at one specific dated snapshot. Promotion updates the manifest only after the graph artifacts already exist.

## Host Runtime Model

On the API host:

- graph releases are stored under `/var/lib/wikiarena/graph/releases/<snapshot_id>/`
- the active graph is exposed through `/var/lib/wikiarena/graph/current/`
- the API reads stable paths from `/etc/wikiarena/wikiarena.env`
- `sync-graph.sh` is safe to run as the `wikiarena` service user
- rollout and deploy wrappers restart `wikiarena-api.service` only after the selected graph is present

This matters because the API loads the graph at process start. Changing files on disk is not enough by itself; a graph rollout must restart the service and verify the active `snapshot_id`.

## GitHub Actions Model

The important production workflows are:

1. `Build Graph`
   - builds a dated graph snapshot
   - uploads graph artifacts to S3
   - can also publish GitHub release assets
2. `Promote Graph`
   - reads the chosen graph metadata
   - writes `graphs/<wiki>/channels/<channel>.json`
   - can optionally trigger immediate rollout
3. `Rollout Graph`
   - runs remote host scripts over SSM
   - syncs the selected channel onto the instance
   - restarts the service
   - verifies `/health` and `/v1/meta`
4. `Build API Bundle`
   - packages application code into an S3 deployment artifact
5. `Deploy API`
   - downloads the selected API bundle
   - updates `/opt/wikiarena/current`
   - restarts the service against the already-promoted graph

GitHub Actions assumes AWS roles over OIDC. No long-lived AWS secrets belong in the repo or in GitHub Actions secrets.

## Common Flows

### Monthly Graph Refresh

1. Run or schedule `Build Graph`
2. Review validation
3. Run `Promote Graph` for the new `dump_date`
4. Let `Promote Graph` trigger `Rollout Graph`, or run rollout explicitly
5. Confirm `/v1/meta` reports the expected `snapshot_id`

This path should not require Terraform edits and should not require `Deploy API`.

### Code-Only Deploy

1. Push app changes
2. Run `Build API Bundle`
3. Run `Deploy API`
4. Confirm `/health`
5. Confirm `/v1/meta` still reports the intended promoted graph

This path should not change the graph channel.

### Fresh Host Bring-Up

1. Apply Terraform from the infra repo
2. Ensure a dated graph snapshot exists in S3
3. Run `Promote Graph`
4. Run `Rollout Graph` or `Deploy API`
5. Smoke test `/health`, `/v1/meta`, and `/v1/solve`

## Verification

The minimum useful production checks are:

- `GET /health`
- `GET /v1/meta`
- verify `snapshot_id` matches the promoted graph
- one real `POST /v1/solve` smoke test after material runtime changes

If a rollout succeeds but `snapshot_id` does not change, the service restarted without actually switching graphs. Treat that as a failed rollout.
