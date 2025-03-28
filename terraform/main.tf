terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}

# Configure Kubernetes provider
provider "kubernetes" {
  config_path = "~/.kube/config"
}

# Create namespace for our application
resource "kubernetes_namespace" "onprem_cloud_connector" {
  metadata {
    name = "onprem-cloud-connector"
    
    labels = {
      environment = var.environment
      managed-by  = "terraform"
    }
  }
}

# Create secrets for certificates and tokens
resource "kubernetes_secret" "tls_certificates" {
  metadata {
    name      = "tls-certificates"
    namespace = kubernetes_namespace.onprem_cloud_connector.metadata[0].name
  }

  data = {
    "ca.crt"     = file(var.ca_cert_path)
    "server.crt" = file(var.server_cert_path)
    "server.key" = file(var.server_key_path)
  }

  type = "kubernetes.io/tls"
}

# Create ConfigMap for application configuration
resource "kubernetes_config_map" "app_config" {
  metadata {
    name      = "app-config"
    namespace = kubernetes_namespace.onprem_cloud_connector.metadata[0].name
  }

  data = {
    "config.yaml" = <<-EOT
      token_rotation:
        enabled: true
        interval_hours: 24
      
      security:
        min_tls_version: "TLS1.2"
        enable_mtls: true
        
      monitoring:
        prometheus_enabled: true
        logging_level: "INFO"
        
      pubsub:
        message_retention_days: 7
        dead_letter_enabled: true
        max_retry_attempts: 3
    EOT
  }
}

# Deploy the registry service
resource "kubernetes_deployment" "registry" {
  metadata {
    name      = "registry"
    namespace = kubernetes_namespace.onprem_cloud_connector.metadata[0].name
    
    labels = {
      app = "registry"
    }
  }

  spec {
    replicas = var.registry_replicas

    selector {
      match_labels = {
        app = "registry"
      }
    }

    template {
      metadata {
        labels = {
          app = "registry"
        }
      }

      spec {
        container {
          name  = "registry"
          image = "onprem-cloud-connector-registry:latest"

          port {
            container_port = 8080
          }

          volume_mount {
            name       = "tls-certs"
            mount_path = "/etc/certs"
            read_only  = true
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/config"
            read_only  = true
          }

          resources {
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
            requests = {
              cpu    = "200m"
              memory = "256Mi"
            }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 30
            period_seconds       = 10
          }
        }

        volume {
          name = "tls-certs"
          secret {
            secret_name = kubernetes_secret.tls_certificates.metadata[0].name
          }
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.app_config.metadata[0].name
          }
        }
      }
    }
  }
}

# Create service for registry
resource "kubernetes_service" "registry" {
  metadata {
    name      = "registry"
    namespace = kubernetes_namespace.onprem_cloud_connector.metadata[0].name
  }

  spec {
    selector = {
      app = kubernetes_deployment.registry.metadata[0].labels.app
    }

    port {
      port        = 443
      target_port = 8080
      protocol    = "TCP"
    }

    type = "LoadBalancer"
  }
} 