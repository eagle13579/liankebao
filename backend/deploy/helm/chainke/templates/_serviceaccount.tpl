{{- define "chainke.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "chainke.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
