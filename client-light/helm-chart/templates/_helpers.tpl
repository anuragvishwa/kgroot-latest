{{- define "kg-rca-agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kg-rca-agent.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "kg-rca-agent.labels" -}}
app.kubernetes.io/name: {{ include "kg-rca-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
client-id: {{ .Values.client.id | quote }}
{{- end }}

{{- define "kg-rca-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kg-rca-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
