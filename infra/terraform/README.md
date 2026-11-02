# Infrastructure as code

Provider-agnostic platform bootstrap written in HCL that is valid for both
[OpenTofu](https://opentofu.org) (used in CI, open source) and Terraform. It uses only the
`kubernetes` provider, so it runs against **any** conformant cluster (kind, a managed cloud
cluster, on-prem) with nothing but a kubeconfig.

```text
infra/terraform/
├── modules/
│   └── namespace/     namespace + Pod Security labels + ResourceQuota + LimitRange + default-deny NetworkPolicy
└── envs/
    └── dev/           example root module: provider config, variables, one module call, no secrets, no backend
```

## What the `namespace` module gives you

| Resource                | Why                                                                           |
| ----------------------- | ----------------------------------------------------------------------------- |
| Pod Security labels     | `restricted` by default; the Helm chart in `deploy/helm/app` complies with it |
| `ResourceQuota`         | One app cannot starve the cluster                                             |
| `LimitRange`            | Containers without explicit resources still get requests and limits           |
| default-deny `NetworkPolicy` | Nothing talks to anything until allowed; enable `networkPolicy.enabled` in the chart for the allow rules |

## Use it

```bash
cd infra/terraform/envs/dev
cp terraform.tfvars.example terraform.tfvars   # set kube_context
tofu init
tofu plan
tofu apply
```

Validate without any cluster or credentials (this is what CI does):

```bash
tofu init -backend=false && tofu validate && tofu fmt -check -recursive ../..
```

`kube_context` is a required variable on purpose: an apply must never silently target whichever
context is currently selected in your kubeconfig.

## Where cloud-specific modules plug in

This template deliberately ships no cloud code. Add sibling modules next to `namespace` and call
them from an environment's `main.tf`; the app layer stays unchanged because the contract between
layers is small:

| Layer you add           | Example module path           | Hands to the app layer                                                      |
| ----------------------- | ----------------------------- | --------------------------------------------------------------------------- |
| Managed Kubernetes      | `modules/cluster-<cloud>`     | kubeconfig / endpoint + auth for the `kubernetes` provider in `envs/<env>`  |
| Managed PostgreSQL      | `modules/postgres-<cloud>`    | A connection URL, stored in a Secret named by `database.existingSecret`     |
| Container registry      | `modules/registry-<cloud>`    | Repository URLs for `backend.image.repository` / `frontend.image.repository` |
| Workload identity / IAM | `modules/identity-<cloud>`    | Annotations for `serviceAccount.annotations`                                |

Guidance:

- **One root module per environment** (`envs/dev`, `envs/staging`, `envs/prod`), each with its own
  remote state. Share code through `modules/`, never by copying files.
- **State is remote, encrypted and locked.** `envs/dev/versions.tf` contains a commented backend
  example; no backend is active so the example works offline.
- **No secrets in `.tf`/`.tfvars`.** Pass credentials through the provider's own mechanism
  (kubeconfig `exec` plugin, workload identity, CI OIDC). Generated secrets (database password)
  belong in a secret manager and reach the cluster as a Kubernetes Secret via External Secrets or
  a CSI driver, referenced by `database.existingSecret`.
- **Pin providers** (`~> x.y`) and commit `.terraform.lock.hcl`. The committed lock file is written
  by OpenTofu; Terraform users should run `terraform init -upgrade` once to re-lock against the
  Terraform registry.
- The security gate (`make security`, Trivy `config` scan) covers this directory, so IaC
  misconfigurations fail the same checks as everything else.
