provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context
}

module "app_namespace" {
  source = "../../modules/namespace"

  name = var.namespace
  labels = {
    "app.kubernetes.io/part-of" = "app"
    environment                 = "dev"
  }

  # Dev is allowed to be small; production should size this from real usage.
  quota = {
    "requests.cpu"    = "2"
    "requests.memory" = "4Gi"
    "limits.cpu"      = "4"
    "limits.memory"   = "8Gi"
    "pods"            = "30"
  }
}
