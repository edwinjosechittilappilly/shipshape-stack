output "namespace" {
  description = "Namespace to pass to `helm upgrade --install --namespace`."
  value       = module.app_namespace.name
}
