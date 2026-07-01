{{/*
链客宝 Backend — Helm 辅助模板
*/}}

{{- define "chainke.name" -}}
{{- default "chainke" .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "chainke.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default "chainke" .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "chainke.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "chainke.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: chainke-backend
{{- end }}

{{- define "chainke.backendSelectorLabels" -}}
app.kubernetes.io/name: {{ include "chainke.name" . }}
app.kubernetes.io/component: api
tier: backend
{{- end }}

{{- define "chainke.agentSelectorLabels" -}}
app.kubernetes.io/name: {{ include "chainke.name" . }}
app.kubernetes.io/component: agent-runtime
tier: agent
{{- end }}

{{- define "chainke.imagePullSecrets" -}}
{{- if .Values.imagePullSecrets }}
imagePullSecrets:
{{- range .Values.imagePullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{- define "chainke.configMapEnv" -}}
envFrom:
  - configMapRef:
      name: {{ include "chainke.fullname" . }}-config
{{- if .Values.existingSecret }}
  - secretRef:
      name: {{ .Values.existingSecret }}
{{- end }}
{{- end }}
