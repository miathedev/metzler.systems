---
# Leave the homepage title empty to use the site title
title: ''
summary: ''
date: 2026-01-05
type: landing

sections:
  # Developer Hero - name, typewriter role, social links, one CTA
  - block: dev-hero
    id: hero
    content:
      username: me
      show_status: true
      show_scroll_indicator: false
      typewriter:
        enable: true
        prefix: "I build"
        strings:
          - "self-hosted Kubernetes clusters"
          - "observability stacks that answer why"
          - "HA platforms that fail over, not fail"
          - "Linux infrastructure since childhood"
        type_speed: 70
        delete_speed: 40
        pause_time: 2500
      cta_buttons:
        - text: View projects
          url: "#projects"
          icon: arrow-down
    design:
      style: centered
      avatar_shape: circle
      spacing:
        padding: ["6rem", "0", "4rem", "0"]

  # Filterable Portfolio - Alpine.js powered project filtering
  - block: portfolio
    id: projects
    content:
      title: "Featured projects"
      subtitle: "Infrastructure, embedded and homelab projects I built and run"
      count: 6
      filters:
        folders:
          - projects
      buttons:
        - name: All
          tag: '*'
        - name: Kubernetes
          tag: Kubernetes
        - name: DevOps
          tag: DevOps
        - name: Homelab
          tag: Homelab
      default_button_index: 0
    design:
      columns: 2
      spacing:
        padding: ["4rem", "0", "4rem", "0"]

  # Visual Tech Stack - Icons organized by category
  - block: tech-stack
    id: skills
    content:
      title: "Tech stack"
      subtitle: "What I run in production and in my homelab"
      categories:
        - name: Platform
          items:
            - name: Kubernetes
              icon: devicon/kubernetes
            - name: Docker
              icon: devicon/docker
            - name: Helm
              icon: devicon/helm
            - name: Proxmox
              icon: devicon/proxmox
        - name: OS & Automation
          items:
            - name: Linux
              icon: devicon/linux
            - name: Ansible
              icon: devicon/ansible
            - name: Bash
              icon: devicon/bash
            - name: GitLab CI
              icon: devicon/gitlab
        - name: Observability
          items:
            - name: Prometheus
              icon: devicon/prometheus
            - name: Grafana
              icon: devicon/grafana
            - name: OpenTelemetry
              icon: devicon/opentelemetry
            - name: Git
              icon: devicon/git
        - name: Languages & Security
          items:
            - name: Python
              icon: devicon/python
            - name: Rust
              icon: devicon/rust
            - name: Java
              icon: devicon/java
            - name: Vault
              icon: devicon/vault
    design:
      style: grid
      show_levels: false
      spacing:
        padding: ["4rem", "0", "4rem", "0"]

  # Experience Timeline
  - block: resume-experience
    id: experience
    content:
      title: Experience
      date_format: Jan 2006
      items:
        - title: System Engineer & DevOps Engineer
          company: bpm consult ag
          company_url: https://www.bpm-consult.com/
          company_logo: ''
          location: Hägendorf (SO), CH
          date_start: '2024-04-01'
          date_end: ''
          description: |2-
            * Platform behind beeline — ERP & e-commerce for the book/media trade, 50+ online shops on Linux, KVM and InterSystems IRIS
            * Lead Linux system administrator of the entire data centre, incl. incident response for critical outages
            * Observability stack: Prometheus/Mimir, Loki, Alertmanager, OpenTelemetry, IPMI — data-driven root-cause analysis
            * Highly available active/active container platform with CI/CD, central logging and backups
            * Security hardening: internal PKI with offline root CA, HashiCorp Vault, hardware-key MFA, credential rotation, blameless postmortems
            * Tech stack: Linux, Ansible, Python, GitLab CI/CD, Prometheus, Grafana, Vault
        - title: Infrastructure Engineer — freelance cluster operation since Apr 2024
          company: Leo Skull GmbH
          company_url: ''
          company_logo: ''
          location: Oldenburg, DE
          date_start: '2023-06-01'
          date_end: ''
          description: |2-
            * Migrated production infrastructure from Google Cloud to a cost-efficient self-hosted Kubernetes cluster
            * HA SaaS environments with automated failover and load balancing; PHP/Laravel apps with RabbitMQ and MongoDB ported into the cluster
            * Monitoring with Prometheus, Grafana, Loki; shift-left security scans in GitLab CI/CD
            * Architecture and operation of SD-WAN and corporate networks
            * Since 04/2024: freelance operation of the migrated cluster — maintenance, consulting, support
            * Tech stack: Kubernetes, Docker, Ansible, Bash, Python, GitLab CI/CD
        - title: DevOps and Embedded Systems
          company: engram GmbH
          company_url: ''
          company_logo: ''
          location: Bremen, DE
          date_start: '2019-01-01'
          date_end: '2023-01-31'
          description: |2-
            * Migrated branch display systems (digital signage, customer guidance) from Windows to Linux — replacing costly Windows licences
            * Build and optimisation of CI/CD pipelines; QA processes; deployment strategies for display hardware and cloud environments
            * Tech stack: Linux, CI/CD, deployment automation
        - title: Working Student — DevOps
          company: hmmh multimediahaus AG
          company_url: ''
          company_logo: ''
          location: Bremen, DE
          date_start: '2018-10-01'
          date_end: '2019-11-30'
          description: |2-
            * Jenkins CI/CD maintenance and modernisation (pipeline parallelisation)
            * JUnit4 to JUnit5 migration; bugfixing in a production Java/Spring e-commerce platform
            * Tech stack: Jenkins, Java, Spring, JUnit
    design:
      columns: '1'
      spacing:
        padding: ["4rem", "0", "4rem", "0"]

  # Recent Blog Posts
  - block: collection
    id: blog
    content:
      title: Recent posts
      subtitle: 'Notes from production: Kubernetes, Linux, observability'
      text: ''
      filters:
        folders:
          - blog
        exclude_featured: false
      count: 3
      order: desc
    design:
      view: card
      columns: 3
      spacing:
        padding: ["4rem", "0", "4rem", "0"]

  # Contact Section
  - block: contact-info
    id: contact
    content:
      title: Get in touch
      subtitle: "Hiring for a Kubernetes, DevOps or SRE role? Let's talk — e-mail: {{< email >}}"
      text: |-
        I'm based in the DE/CH border region — Küssaberg (DE), 5 minutes from
        Bad Zurzach, with a valid G permit (DE→CH) — and open to full-time or contract
        roles. You can also find me on GitHub, LinkedIn and Bandcamp (see Links).
    design:
      columns: '1'
      spacing:
        padding: ["4rem", "0", "4rem", "0"]

  # CTA Card
  - block: cta-card
    content:
      title: "Open to opportunities"
      text: |-
        I'm currently looking for **Kubernetes / DevOps / SRE / platform** roles,
        full-time or contract, in the Zürich / Baden / Aarau / Basel region.

        CV and references on request.
      button:
        text: 'Download CV (PDF)'
        url: uploads/cv-mia-metzler.pdf
        new_tab: true
    design:
      spacing:
        padding: ["4rem", "0", "6rem", "0"]
---
