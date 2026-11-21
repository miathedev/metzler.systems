---
title: "cluster-departure: a train departure board for your Kubernetes cluster"
date: 2026-11-17
summary: "Every Deployment is a station, every replica a track, every pod a train. cluster-departure renders your cluster as a live departure board, FastAPI backend, metrics-server for real CPU/memory numbers, static frontend with sprites. Hopefully your deployments don't get stuck like the Deutsche Bahn."
tags:
  - Kubernetes
  - Homelab
  - Fun
authors:
  - me
featured: false
---

[cluster-departure](https://github.com/miathedev/cluster-departure) is a small toy I built for my homelab: it renders a Kubernetes cluster as a train departure board. Every Deployment is a station, every replica a track, and every pod a train, with live CPU and memory numbers next to each train, so you can see at a glance which workload is hogging the platform.

Hopefully your deployments don't get stuck as often as the Deutsche Bahn.

## How it works

The backend is ~140 lines of FastAPI on the official `kubernetes` Python client. It loads a kubeconfig locally, or the in-cluster config when running inside the cluster, and aggregates Deployments, pods and node/pod metrics into a single `/api/state` payload. The live numbers come from `metrics-server` (`metrics.k8s.io/v1beta1`), no Prometheus needed, the API server already aggregates them. The frontend is plain static HTML/CSS/JS with sprites, served by the same app, open `http://localhost:8000` and enjoy the board.

## Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Needs a kubeconfig (or in-cluster config) and `metrics-server` running in the cluster. Then open http://localhost:8000.

## Why a departure board

Because `kubectl get pods` tells you *that* something runs, but not *how hot* it is. On a single-node homelab the board answers the actual question, "which of these trains is late (and why)", without opening Grafana. The metaphor holds up in practice: a stuck rollout is a delayed departure, a pending pod is a train that never left the station, and a node under pressure is the station master having a day.

Code is public: <https://github.com/miathedev/cluster-departure>
