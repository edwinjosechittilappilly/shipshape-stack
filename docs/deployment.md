# Deployment

How the app is packaged, run locally, and shipped to a cluster. Everything here is exercised by
CI, so the commands below stay true.

## Environments

| Environment | Tool                              | Database                                   | Purpose                                      | Start with                  |
| ----------- | --------------------------------- | ------------------------------------------ | -------------------------------------------- | --------------------------- |
| Local dev   | Vite + uvicorn (no containers)    | Compose `postgres` (`make db-up`)          | Fast inner loop with hot reload              | `make db-up`, package `dev` |
| Compose     | `docker-compose.yml`              | Compose `postgres` with a named volume     | Full stack in containers on one machine      | `make up` → <http://localhost:8080> |
| kind        | Helm chart on a local cluster     | Throwaway pod (`deploy/kind/postgres.yaml`) | Prove the chart, migrations and probes work  | `make kind-e2e`             |
| Real cluster | Helm chart (+ `infra/terraform`) | Managed PostgreSQL, URL from a Secret      | Staging / production                         | `helm upgrade --install …`  |

Rule of thumb: Compose answers "does it run?", kind answers "does it deploy?", and a real cluster
answers "does it hold up?". The same two images are used in all three.

## Images

| Image                                   | Built from           | Notes                                                          |
| --------------------------------------- | -------------------- | -------------------------------------------------------------- |
| `app-backend:local`                     | `backend/Dockerfile`  | Multi-stage uv build, uid 10001, read-only-root-FS compatible  |
| `app-frontend:local`                    | `frontend/Dockerfile` | nginx-unprivileged on 8080, proxies `/api/` to `API_UPSTREAM`  |
| `ghcr.io/<owner>/<repo>/backend\|frontend` | CI                  | Chart defaults are placeholders (`ghcr.io/example-org/...`); override `*.image.repository` |

`make build` builds the local tags through Compose.

## Compose

```bash
make up      # build, start, and wait until every healthcheck passes
make logs    # tail logs
make down    # stop and delete volumes
```

Start order is enforced by health, not sleeps: `postgres` (healthy) → `migrate` (exits 0) →
`backend` (`/readyz` ok) → `frontend` (`/healthz` ok). `docker compose up --wait` therefore only
returns when the stack is usable. Ports are overridable: `POSTGRES_PORT`, `BACKEND_PORT`,
`FRONTEND_PORT`. Credentials in the file are throwaway local defaults.

## kind (local Kubernetes)

```bash
make kind-e2e                      # create cluster, build + load images, install, smoke-test, tear down
KEEP_CLUSTER=1 make kind-e2e       # leave the cluster for poking around
SKIP_BUILD=1 make kind-e2e         # reuse existing app-*:local images
scripts/kind-e2e.sh --help         # every knob (CLUSTER_NAME, NAMESPACE, LOCAL_PORT, ...)
```

What the script does, in order: build images → create (or reuse) a single-node cluster → `kind load`
the images → apply the dev-only Postgres → `helm upgrade --install --wait` with
`deploy/kind/values-kind.yaml` (the migration hook Job runs first) → port-forward the frontend →
check `/healthz`, then create, list and delete an item through the nginx `/api` proxy → `helm test`.
On any failure a trap dumps pods, events, Helm status and container logs before cleaning up.

Safety: the script uses its own kubeconfig file and passes `--context kind-<name>` to every
command, so it can never touch whatever cluster your default kubeconfig points at. A cluster that
already existed is kept (only the namespace is deleted); a cluster the script created is deleted
unless `KEEP_CLUSTER=1`.

`deploy/kind/postgres.yaml` is **dev only**: one pod, `emptyDir` storage, hard-coded password.

## Helm chart (`deploy/helm/app`)

Deploys the backend and frontend (Deployment + Service each), a ConfigMap, a ServiceAccount with
token automount off, PodDisruptionBudgets, and a `helm test` pod. Optional: Ingress
(`/api` → backend, `/` → frontend), HorizontalPodAutoscalers, NetworkPolicies. All values are
documented in `values.yaml` and validated by `values.schema.json` (unknown keys and wrong types fail
at `helm lint`/`install` time, so typos do not silently do nothing).

```bash
make helm-lint        # helm lint --strict + helm template
helm upgrade --install app deploy/helm/app \
  --namespace app --create-namespace \
  --set backend.image.digest=sha256:… --set frontend.image.digest=sha256:… \
  --set database.existingSecret=app-database \
  --set ingress.enabled=true --set ingress.host=app.example.com \
  --wait --wait-for-jobs
```

Key values:

| Value                                         | Meaning                                                              |
| --------------------------------------------- | -------------------------------------------------------------------- |
| `backend.image.*`, `frontend.image.*`         | `repository`, `tag` (default: chart `appVersion`), `digest` (wins over tag) |
| `backend.replicaCount`, `*.autoscaling.*`     | Fixed replicas, or an HPA (the chart then omits `replicas`)          |
| `database.existingSecret` / `existingSecretKey` | Secret holding `DATABASE_URL` (default `app-database` / `database-url`) |
| `database.url`                                | **Dev only**: chart creates the Secret; leave `existingSecret` empty |
| `config.appEnv`, `logLevel`, `corsOrigins`    | Non-secret settings (ConfigMap; pods roll when they change)          |
| `frontend.apiUpstream`                        | nginx `/api` target; default is the chart's backend Service          |
| `migration.enabled`, `migration.command`      | The migration hook Job                                               |
| `ingress.*`, `networkPolicy.*`                | Optional exposure and traffic rules                                  |

Hardening applied to every pod: `runAsNonRoot`, fixed numeric UID, `readOnlyRootFilesystem` (writable
`emptyDir` only at `/tmp`, plus nginx's `conf.d`), all capabilities dropped, no privilege
escalation, `seccompProfile: RuntimeDefault`, requests and limits, and topology spread. The
namespace module in `infra/terraform` enforces the `restricted` Pod Security level, which this chart
satisfies.

Probes: **liveness** `/healthz` never touches the database, so a database outage cannot trigger
restart storms; **readiness** `/readyz` checks the database, so pods leave the Service while it is
unreachable. A startup probe covers slow starts without loosening liveness.

## Migrations strategy

Schema changes run **once per release, before new code receives traffic**, never at application
start (replicas would race, and a slow migration would fail probes).

- Compose: the one-shot `migrate` service runs `alembic upgrade head`; `backend` waits for it to
  complete successfully.
- Kubernetes: a Helm `pre-install,pre-upgrade` hook Job (same backend image, command
  `alembic upgrade head`). If it fails, the release fails and the old pods keep serving.
  `--wait-for-jobs` plus `--wait` make CI fail fast; failed Jobs are kept for `kubectl logs`.

Because old pods run against the new schema during a rolling update, migrations must be
**backward compatible** (expand/contract): add nullable columns and new tables first; remove or
rename in a later release after no running version reads the old shape. `helm rollback` restores old
manifests and images but **does not undo schema changes**, so a rollback is only safe when the
previous version works with the current schema. Destructive migrations need an explicit plan and a
database backup first.

## Secrets

- **Nothing sensitive in Git, values files, or image layers.** Values files hold references (secret
  names), never secret values.
- The application reads `DATABASE_URL` from a Kubernetes Secret named by `database.existingSecret`.
  Create it out-of-band:

  ```bash
  kubectl -n app create secret generic app-database \
    --from-literal=database-url='postgresql+psycopg://USER:PASSWORD@HOST:5432/DB'
  ```

  In real environments let a controller own it (External Secrets Operator, Secrets Store CSI
  driver, Sealed Secrets) sourced from your cloud secret manager, and rotate there.
- `database.url` (chart-created Secret) exists for demos only: the URL lands in Helm release
  history in clear text.
- Prefer short-lived federated (OIDC) credentials over stored cloud keys in pipelines; `gitleaks`
  (pre-commit) and Trivy (`make security`) scan for committed secrets.

## Rollback

```bash
helm history app -n app                # list revisions
helm rollback app <revision> -n app --wait
```

Rollback re-applies the previous revision's manifests (including its image digests). Check the
migration caveat above first. For Compose, check out the previous tag and run `make up`.

## Image promotion by digest

Build once, promote the same bytes. Tags are mutable; digests are not.

1. CI builds each image once per commit and pushes it to the registry, recording the digest
   (`sha256:…`) from the push output.
2. Staging deploys that digest: `--set backend.image.digest=sha256:…` (the chart renders
   `repo@sha256:…`; the tag is ignored).
3. After verification, **promote by reusing the identical digest** in the production values/command.
   Never rebuild for production, and never deploy a floating tag like `latest`.
4. Optionally add a human-readable tag (`v1.4.0`) to the same digest for traceability, and sign or
   attest the image where the platform supports it.

Keep a per-environment values file (`values-staging.yaml`, `values-prod.yaml`) in your deployment
repository or pipeline and update only the digests on promotion, so every promotion is a reviewable
diff and every rollback is a revert.

## Infrastructure as code

`infra/terraform` bootstraps the namespace (Pod Security, quota, limit range, default-deny
NetworkPolicy) on any cluster; see its README for where cloud-specific modules (managed Kubernetes,
managed PostgreSQL, registry) plug in. It is valid for both OpenTofu and Terraform; CI uses
OpenTofu.

## Security scanning

`make security` runs Trivy with the same policy as CI (`trivy.yaml`, suppressions in `.trivyignore`):
dependency vulnerabilities and secrets in the tree, IaC misconfiguration (Dockerfiles, Helm
rendered with every optional feature enabled, Terraform), and the built images when present. Reports
land in `reports/security/` (JSON, SARIF, `summary.md`). See `docs/security.md` for how CI publishes
them for private versus public repositories.
