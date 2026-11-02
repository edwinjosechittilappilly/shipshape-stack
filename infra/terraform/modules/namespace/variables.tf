variable "name" {
  description = "Namespace name (DNS-1123 label)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.name)) && length(var.name) <= 63
    error_message = "name must be a DNS-1123 label: lowercase alphanumerics or '-', max 63 characters."
  }
}

variable "labels" {
  description = "Extra labels for the namespace. Pod Security Admission labels are managed via pod_security_level."
  type        = map(string)
  default     = {}
}

variable "pod_security_level" {
  description = "Pod Security Standards level enforced on the namespace (privileged, baseline or restricted). The Helm chart in deploy/helm/app meets 'restricted'."
  type        = string
  default     = "restricted"

  validation {
    condition     = contains(["privileged", "baseline", "restricted"], var.pod_security_level)
    error_message = "pod_security_level must be privileged, baseline or restricted."
  }
}

variable "quota" {
  description = "ResourceQuota hard limits. Set to null to skip creating a quota."
  type        = map(string)
  default = {
    "requests.cpu"    = "4"
    "requests.memory" = "8Gi"
    "limits.cpu"      = "8"
    "limits.memory"   = "16Gi"
    "pods"            = "50"
  }
}

variable "default_container_limits" {
  description = "LimitRange defaults applied to containers that declare no resources."
  type = object({
    default         = map(string)
    default_request = map(string)
  })
  default = {
    default         = { cpu = "500m", memory = "512Mi" }
    default_request = { cpu = "100m", memory = "128Mi" }
  }
}

variable "default_deny_network_policy" {
  description = "Create a default-deny (ingress + egress) NetworkPolicy. Workloads then need explicit allow rules (the Helm chart's networkPolicy.enabled=true provides them). Requires a CNI that enforces NetworkPolicy."
  type        = bool
  default     = true
}
