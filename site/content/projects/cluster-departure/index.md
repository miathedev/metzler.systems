---
title: "cluster-departure"
date: 2026-11-17
summary: "A train-departure board for your Kubernetes cluster, FastAPI backend aggregating Deployments, pods and live metrics-server numbers into one /api/state payload, rendered as a static sprite frontend. Deutsche Bahn, but for Kubernetes."
tags:
  - Kubernetes
  - Homelab
tech_stack:
  - Python
  - FastAPI
  - Kubernetes
  - metrics-server
links:
  - type: github
    url: https://github.com/miathedev/cluster-departure
    label: Code
featured: false
status: "Live"
role: "Solo project"
duration: "2026"
team_size: 1
highlights:
  - "Deployment = station, replica = track, pod = train"
  - "Live CPU/memory per pod via metrics-server, no Prometheus needed"
  - "Single /api/state endpoint, static sprite frontend served by the same app"
---

`cluster-departure` renders a Kubernetes cluster as a live train departure board: each Deployment is a station, each replica a track, each pod a train with its current CPU and memory next to it.

The backend is a small FastAPI app using the official `kubernetes` Python client, kubeconfig locally, in-cluster config in the cluster, plus `metrics-server` for the live numbers. The whole board is one `/api/state` payload rendered by a static sprite frontend.

Code: <https://github.com/miathedev/cluster-departure>.
