terraform {
  required_version = ">= 1.6.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.5"
    }
  }

  # No backend is configured on purpose: state stays local, so this example never needs cloud
  # credentials and can be validated with `init -backend=false`. For a real environment keep
  # state remote, encrypted and locked, e.g. S3 (use_lockfile) or any backend your platform offers:
  #
  # backend "s3" {
  #   bucket       = "my-org-terraform-state"
  #   key          = "app/dev/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}
