variable "kubeconfig_path" {
  description = "Path to the kubeconfig of the target cluster. Credentials stay in that file, never in Terraform variables."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "Kubeconfig context to use. Required, so an apply can never silently hit whatever context happens to be current."
  type        = string
}

variable "namespace" {
  description = "Namespace for the application (matches the Helm release namespace)."
  type        = string
  default     = "app"
}
