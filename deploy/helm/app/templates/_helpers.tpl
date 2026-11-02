{{/* Chart name, truncated to the 63-char DNS label limit. */}}
{{- define "app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "app.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels shared by every object. */}}
{{- define "app.labels" -}}
helm.sh/chart: {{ include "app.chart" . }}
app.kubernetes.io/name: {{ include "app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Immutable selector labels for one component. Usage: include "app.selectorLabels" (dict "ctx" . "component" "backend") */}}
{{- define "app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "app.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "app.componentLabels" -}}
{{ include "app.labels" .ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "app.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "app.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Image reference: digest wins over tag. Usage: include "app.image" (dict "image" .Values.backend.image "ctx" .) */}}
{{- define "app.image" -}}
{{- if .image.digest -}}
{{- printf "%s@%s" .image.repository .image.digest -}}
{{- else -}}
{{- printf "%s:%s" .image.repository (default .ctx.Chart.AppVersion .image.tag) -}}
{{- end -}}
{{- end -}}

{{/* Name/key of the Secret that holds DATABASE_URL. */}}
{{- define "app.databaseSecretName" -}}
{{- if .Values.database.existingSecret -}}
{{- .Values.database.existingSecret -}}
{{- else -}}
{{- printf "%s-database" (include "app.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "app.databaseSecretKey" -}}
{{- if .Values.database.existingSecret -}}
{{- .Values.database.existingSecretKey -}}
{{- else -}}
database-url
{{- end -}}
{{- end -}}

{{/* DATABASE_URL env entry shared by the backend and the migration Job. */}}
{{- define "app.databaseEnv" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "app.databaseSecretName" . }}
      key: {{ include "app.databaseSecretKey" . }}
{{- end -}}

{{- define "app.frontendApiUpstream" -}}
{{- if .Values.frontend.apiUpstream -}}
{{- .Values.frontend.apiUpstream -}}
{{- else -}}
{{- /* Fully qualified: nginx resolves this at request time with its own resolver, which ignores the pod's DNS search domains. */ -}}
{{- printf "http://%s-backend.%s.svc.%s:%d" (include "app.fullname" .) .Release.Namespace .Values.clusterDomain (int .Values.backend.service.port) -}}
{{- end -}}
{{- end -}}
