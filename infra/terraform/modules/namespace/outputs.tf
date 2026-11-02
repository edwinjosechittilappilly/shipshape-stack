output "name" {
  description = "Name of the created namespace (use this to create dependent resources)."
  value       = kubernetes_namespace_v1.this.metadata[0].name
}
