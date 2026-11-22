# syntax=docker/dockerfile:1
# Dockerfile: Image fuer den Load-Service (k6-Run als Kubernetes-Job) — python:3.14-slim per sha256-Digest
# gepinnt, non-root (USER 101), PYTHONDONTWRITEBYTECODE (readOnlyRootFilesystem).

# Base-Image-Tag ist floating — ein rebuild holt gefixte OS-Pakete aus dem Repo.
FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --chmod=0644: lokale Checkouts mit restriktivem umask (Datei 600) duerfen
# das Image nicht brechen — USER 101 muss die Dateien lesen koennen.
# app/ als Ganzes: main.py + Module (config, k8s).
COPY --chmod=0644 app/ .

USER 101
EXPOSE 8080
# ENTRYPOINT statt CMD: das Deployment hängt nur noch --root-path als args an
# (K8s-args ersetzen das Image-CMD), der Befehl lebt an genau einer Stelle.
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
