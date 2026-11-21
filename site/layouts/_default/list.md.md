{{- /* .md-Mirror einer Liste (Sektion/Taxonomie/Term): roher Markdown-Content der _index.md plus Liste der Unterseiten (jeweils deren .md-Mirror). */ -}}
# {{ .Title }}

{{ .RawContent }}
{{ range .Pages }}
- [{{ .Title }}]({{ .Permalink }}index.md)
{{- end }}
