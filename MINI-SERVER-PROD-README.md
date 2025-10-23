# mini-server-prod Audit

This README inventories `mini-server-prod`, highlights every linkage to folders outside of it, and flags content that is currently unsafe or useless to follow. Use it as the source of truth before touching this deployment bundle.

## Status Legend

- `Active` – Safe to rely on as-is.
- `Needs update` – Partially correct but contains drift that will trip users today.
- `Useless` – Misleading enough that it should be ignored until rewritten.
- `Sensitive` – Contains secrets and should not be in git.

## External Linkages

| Reference | Description |
|-----------|-------------|
| `mini-server-prod/compose/docker-compose.yml#L152` | Builds the alerts-enricher image from `../alerts-enricher`, so that repository must exist when running Compose. |
| `mini-server-prod/compose/docker-compose.yml#L180` | Builds the graph-builder from `../kg`. Multi-client overrides reuse the same relative build context. |
| `mini-server-prod/compose/docker-compose.yml#L234` | Builds the API from `../kg-api`. A missing sibling directory will break `docker compose`. |
| `mini-server-prod/compose/docker-compose.multi-client.yml#L23` | Extra graph-builder services also rely on `../kg` for their build context. |
| `mini-server-prod/generate-multi-client-compose.sh:112` | Auto-generated overrides point to `../kg`, so the script inherits the same dependency. |
| `mini-server-prod/DYNAMIC-CLIENT-DISCOVERY.md:153` | Documentation depends on `../client-light/helm-chart` for end-to-end instructions. |
| `mini-server-prod/MULTI-TENANT-SETUP.md:411` | Same Helm reference as above for client configuration. |
| `mini-server-prod/ENV-VARIABLE-FLOW.md:118` | Points to implementation details in `../../kg/graph-builder.go`. Keep that file in sync with docs. |
| `mini-server-prod/docs/TROUBLESHOOTING.md:758` | Assumes `../.env` and `../docker-compose*.yml` exist when capturing troubleshooting bundles. |

## Top-Level Inventory

| Path | Purpose | Status |
|------|---------|--------|
| `mini-server-prod/.env` | Production-style environment file with real secrets committed. | Sensitive – replace with secret management (never commit). |
| `mini-server-prod/.env.example` | Authoritative template for environment variables. | Active. |
| `mini-server-prod/CONSUMER-GROUP-MANAGEMENT.md` | Explains Kafka consumer group auto-creation logic with code references. | Active. |
| `mini-server-prod/DEPLOYMENT-CHECKLIST.md` | Linear deployment checklist. | Useless – references `docker-compose.yml` that is no longer in this folder, so commands fail. |
| `mini-server-prod/DYNAMIC-CLIENT-DISCOVERY.md` | Dynamic multi-tenant how-to. | Needs update – main flow is right but every `docker compose -f docker-compose.yml` command is wrong. |
| `mini-server-prod/ENV-VARIABLE-FLOW.md` | Diagrams how Compose env vars reach Go code. | Active. |
| `mini-server-prod/MULTI-TENANT-SETUP.md` | Overview of multi-tenant architecture and operations. | Needs update – suffers from the same stale command paths as above. |
| `mini-server-prod/QUICK-START.md` | 15-minute deployment instructions. | Useless – directs you to `docker compose up -d` in this directory, which fails immediately. |
| `mini-server-prod/README.md` | Legacy overview (was meant to be the entry point). | Useless – lists files that do not exist anymore (e.g., `scripts/install-docker.sh`, top-level `docker-compose.yml`). |
| `mini-server-prod/SERVICES-EXPLAINED.md` | Service-by-service breakdown. | Needs update – still talks about `kg-kafka-proxy` and other services missing from Compose. |
| `mini-server-prod/START-HERE.md` | Onboarding map linking to the rest of the docs. | Useless – mirrors the stale tree from the old layout. |
| `mini-server-prod/STEP-BY-STEP-GUIDE.md` | Long-form production deployment guide. | Useless – every Compose command assumes a non-existent root file. |
| `mini-server-prod/compose/` | Authoritative Compose bundle (see details below). | Active. |
| `mini-server-prod/config/` | Prometheus and Grafana provisioning. | Active (see cautions below). |
| `mini-server-prod/discover-client-ids.sh` | Uses kafka-console-consumer to print discovered `client_id`s. | Needs update – generated deployment command still assumes `docker-compose.yml` in the same directory. |
| `mini-server-prod/docker-compose.ssl.yml` | SSL overlay extending the main Compose file. | Needs update – comments still reference the old path even though the overlay continues to work. |
| `mini-server-prod/docs/` | Deep-dive docs (architecture, troubleshooting, etc.). | Needs update – many examples still reference the removed Compose path. |
| `mini-server-prod/generate-multi-client-compose.sh` | Auto-generates per-client graph-builder overrides. | Active – header comment is stale but emitted commands use `compose/`. |
| `mini-server-prod/scripts/` | Operational automation scripts. | Active (see per-script notes). |
| `mini-server-prod/ssl/` | Placeholder for generated certificates. | Active – empty holder for `setup-ssl.sh`. |

## Compose Directory

| Path | Purpose | Status |
|------|---------|--------|
| `mini-server-prod/compose/docker-compose.yml` | Source of truth for single-tenant deployment; builds app images from sibling repos. | Active. |
| `mini-server-prod/compose/docker-compose.multi-client.yml` | Static example overlay for three named clients. | Active. |
| `mini-server-prod/compose/README.md` | Accurate usage notes for the current layout. | Active. |

## Config Directory

| Path | Purpose | Status |
|------|---------|--------|
| `mini-server-prod/config/prometheus.yml` | Prometheus scrape configuration. | Needs update – only scrapes `graph-builder:9090`, so multi-client set-ups miss metrics. |
| `mini-server-prod/config/grafana/datasources/datasources.yml` | Sets Prometheus and Neo4j data sources. | Needs update – hardcodes Grafana Neo4j password (`anuragvishwa`) instead of pulling from env. |
| `mini-server-prod/config/grafana/dashboards/dashboards.yml` | Tells Grafana where to load dashboards. | Active. |

## Script Highlights

| Path | Purpose | Status |
|------|---------|--------|
| `mini-server-prod/scripts/setup-ubuntu.sh` | Installs Docker, configures UFW, and tunes the host. | Active. |
| `mini-server-prod/scripts/setup-ssl.sh` | Generates Kafka keystore/truststore material and patches `.env`. | Active – be aware it echoes old Compose commands when finished. |
| `mini-server-prod/scripts/create-topics.sh` | Creates all Kafka topics with defaults. | Active. |
| `mini-server-prod/scripts/test-services.sh` | Runs health checks against containers and ports. | Active. |
| `mini-server-prod/scripts/backup.sh` | Archives Neo4j data, Kafka metadata, and configs. | Needs update – copies `docker-compose*.yml` from the wrong location so the main file is missed. |

## Documentation Set

- `mini-server-prod/docs/ARCHITECTURE.md` – still accurate conceptually.
- `mini-server-prod/docs/BACKUP-RESTORE.md` – walks through restore steps; review Compose path references before using.
- `mini-server-prod/docs/MONITORING.md` – describes dashboards; assumes default datasource passwords.
- `mini-server-prod/docs/SECURITY.md` – hardening checklist; relies on `.env` values.
- `mini-server-prod/docs/TROUBLESHOOTING.md` – **currently useless** for command snippets because it assumes `docker-compose.yml` lives one directory up.

## Files Currently Useless

- `mini-server-prod/README.md`
- `mini-server-prod/START-HERE.md`
- `mini-server-prod/QUICK-START.md`
- `mini-server-prod/STEP-BY-STEP-GUIDE.md`
- `mini-server-prod/DEPLOYMENT-CHECKLIST.md`
- `mini-server-prod/docs/TROUBLESHOOTING.md`

Each of the above has drifted far enough from the actual layout that following the instructions will fail or send operators to missing files. Treat them as placeholders until they are rewritten around `compose/docker-compose.yml`.

## Recommended Next Steps

1. Delete or vault `mini-server-prod/.env`; ship only `.env.example`.
2. Refresh the broken onboarding docs so they point at `compose/docker-compose.yml`.
3. Patch the lingering command snippets in scripts (`discover-client-ids.sh`, `setup-ssl.sh`, `backup.sh`) to reference the correct Compose file path.
4. Update Grafana provisioning to read credentials from environment variables instead of hardcoded defaults.
