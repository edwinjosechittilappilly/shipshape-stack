# A namespace with the guard rails every workload namespace should have:
#   - Pod Security Admission labels (restricted by default)
#   - ResourceQuota: one team/app cannot starve the cluster
#   - LimitRange: containers without explicit resources still get sane requests/limits
#   - default-deny NetworkPolicy: nothing talks to anything until a rule says so

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.name
    labels = merge(var.labels, {
      "app.kubernetes.io/managed-by"       = "terraform"
      "pod-security.kubernetes.io/enforce" = var.pod_security_level
      "pod-security.kubernetes.io/audit"   = var.pod_security_level
      "pod-security.kubernetes.io/warn"    = var.pod_security_level
    })
  }
}

resource "kubernetes_resource_quota_v1" "this" {
  count = var.quota == null ? 0 : 1

  metadata {
    name      = "default"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    hard = var.quota
  }
}

resource "kubernetes_limit_range_v1" "this" {
  metadata {
    name      = "default"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    limit {
      type            = "Container"
      default         = var.default_container_limits.default
      default_request = var.default_container_limits.default_request
    }
  }
}

resource "kubernetes_network_policy_v1" "default_deny" {
  count = var.default_deny_network_policy ? 1 : 0

  metadata {
    name      = "default-deny-all"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    # An empty selector matches every pod in the namespace.
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }
}
