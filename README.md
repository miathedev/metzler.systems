# Metzler.systems Webseite

## Quellen:
* Hugo Template: https://github.com/HugoBlox/hugo-theme-developer-portfolio

## Pre-Commit-Hooks

Einmalig pro Clone aktivieren:

```sh
git config core.hooksPath .githooks
```

Die Hooks in `.githooks/` rufen `pre-commit.sh` im Repo-Root auf. Dort laufen
alle lokalen Checks. Neue Checks in `pre-commit.sh` als `check_<name>()`
definieren und in der `CHECKS`-Liste registrieren. Einzelne Checks
ueberspringen: `SKIP=gitleaks git commit ...`

Aktuelle Checks:
* `pre-commit`: gitleaks-Scan der gestageten Aenderungen (wird beim ersten
  Lauf automatisch als gepinnte Version nach `.bin/` installiert)
* `commit-msg`: Commit-Style (siehe unten)

## Commit-Style

`<Topic>: <beschreibung>` — z.B. `Fix: kyverno admission ...` oder
`chore(website): image auf <sha> [skip ci]`. Topic ist ein Wort aus Buchstaben
und Ziffern, optional mit Scope in Klammern. Merge-, `fixup!`- und
`squash!`-Commits sind ausgenommen. Erzwungen durch `.githooks/commit-msg`
(Pattern: `COMMIT_MSG_PATTERN` in `pre-commit.sh`).