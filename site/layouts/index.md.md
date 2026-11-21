{{- /* .md-Mirror der Home: maschinenlesbarer Einstieg (Pendant zu llms.txt), verlinkt die .md-Mirrors aller Seiten. */ -}}
# {{ site.Title }}
{{- with site.Params.hugoblox.identity.description }}
> {{ . }}
{{- end }}

## Pages
{{ range site.RegularPages.ByTitle }}
- [{{ .Title }}]({{ .Permalink }}index.md)
{{- end }}
