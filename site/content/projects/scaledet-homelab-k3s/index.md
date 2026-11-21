---
title: "ScaleDet homelab on k3s"
date: 2026-11-03
summary: "Splitting an internet-radio training-data harvester into microservices on a single-node k3s homelab, PostgreSQL as the canonical store (audio snippets as bytea), Redis as the task queue, a GPU training Job with a fixed evaluation gate. Doubles as CKA exam prep."
tags:
  - Kubernetes
  - DevOps
  - Homelab
tech_stack:
  - k3s
  - Helm
  - PostgreSQL
  - Redis
  - Python
  - GitLab CI
links:
  - type: site
    url: /blog/2026-11-03-scaledet-homelab-k3s/
    label: Blog post
featured: true
status: "In progress"
role: "Solo project"
duration: "since early 2026"
team_size: 1
highlights:
  - "17 dependency-ordered tickets, each mapped to an official CKA domain"
  - "Listener/labeler pods sharded with claims/leases, kill drills < 2.5 min"
  - "PostgreSQL as the only canonical store, audio snippets as bytea, never CSVs"
  - "Training Job on the RTX GPU promotes weights only through a fixed evaluation gate"
---

ScaleDet is a VST3/AU plugin for the Akai MPC X that shows the musical key and scale of the playing audio in real time. The CNN behind it needs labeled training data, so the homelab harvests it from public internet radio, politely and rate-limited, and trains on the GPU.

The project is organized as 17 tickets that double as structured CKA preparation: storage, workloads, scheduling, Jobs, Secrets, NetworkPolicy, RBAC, theory first, then the ticket on the real cluster, then Killercoda drills for what a single node can't cover.

Full writeup in the [blog post](/blog/2026-11-03-scaledet-homelab-k3s/).
