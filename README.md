# Metzler.systems Webseite

## Quellen:
* Hugo Template: https://github.com/HugoBlox/hugo-theme-developer-portfolio

## Pre-Commit-Hooks

Einmalig pro Clone aktivieren:

```sh
git config core.hooksPath .githooks
```

Der Hook `.githooks/pre-commit` ruft `pre-commit.sh` im Repo-Root auf. Dort
laufen alle lokalen Checks (aktuell: gitleaks-Scan der gestageten Aenderungen;
wird beim ersten Lauf automatisch als gepinnte Version nach `.bin/`
installiert). Neue Checks in `pre-commit.sh` als `check_<name>()` definieren
und in der `CHECKS`-Liste registrieren. Einzelne Checks ueberspringen:
`SKIP=gitleaks git commit ...`