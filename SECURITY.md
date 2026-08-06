# Security Policy

## Supported versions

Security updates are applied to the latest revision of the default branch and the latest published release.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private vulnerability reporting or Security Advisory feature for this repository and include:

- affected version or commit;
- reproduction steps and expected impact;
- relevant configuration without credentials or personal photos;
- a suggested remediation, if known.

You should receive an acknowledgement within seven days. Please allow time for a fix and coordinated disclosure.

## Deployment guidance

Generate secrets locally, keep the `secrets/` directory outside version control, run the container as its non-root user, and place Internet-facing installations behind HTTPS. Avoid exposing PostgreSQL and monitoring services outside a trusted network.
