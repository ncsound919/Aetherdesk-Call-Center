# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| `main`  | :white_check_mark: |
| older   | :x:                |

The `main` branch receives security updates. Older branches and tags are not maintained.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report privately via one of these channels (in order of preference):

1. **GitHub private vulnerability reporting**:
   https://github.com/ncsound919/Aetherdesk-Call-Center/security/advisories/new
2. **Email**: security@aetherdesk.com (PGP key on request)

Include in your report:

- A clear description of the vulnerability and its impact
- Steps to reproduce, or a proof-of-concept
- The affected component(s) and version/commit SHA
- Your name / handle for credit (optional)

## Response Targets

| Stage             | Target time |
|-------------------|-------------|
| Initial ack       | 3 business days |
| Triage + severity | 7 business days |
| Patch (critical)  | 14 days |
| Patch (high)      | 30 days |
| Patch (medium)    | 90 days |
| Patch (low)       | next release |
| Public disclosure | after patch is available |

We will coordinate disclosure timing with you. Credit is given on request.

## Scope

In scope:

- Authentication / authorization bypass
- Tenant isolation / IDOR
- Secret exposure (in code, history, logs, or responses)
- Injection (SQLi, command, prompt, template)
- SSRF, RCE, path traversal
- Cryptographic misuse
- Dependency vulnerabilities with practical exploit paths

Out of scope:

- Vulnerabilities requiring physical access
- Denial of service via unauthenticated volume
- Missing security headers that have no concrete impact
- Self-XSS
- Issues in forks or third-party services we don't control

## Safe Harbor

We will not pursue legal action against researchers who:

- Make a good-faith effort to avoid privacy violations, data destruction, or service disruption
- Only interact with accounts they own or have explicit permission to access
- Stop testing immediately if they encounter user data
- Report findings privately as described above

Thank you for helping keep Aetherdesk and its users safe.
