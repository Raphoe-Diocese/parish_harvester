# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it by:

1. **DO NOT** open a public GitHub issue
2. Email the repository owner directly through their GitHub profile
3. Include detailed information about the vulnerability and steps to reproduce

We will respond within 48 hours and work with you to address the issue.

---

## Known Security Issues

### Chrome extension `key` field (public, not private)

`extension/manifest.json` holds the **public** extension key. That keeps the unpacked extension ID stable when Frank loads the zip. It is **not** the private `.pem` used to sign a Chrome Web Store package.

C2 dropped auto-update. The public `key` stays on purpose. Do not remove it, and do not treat it as a leaked private key.

---

## Secure Development Practices

### Environment Variables

Never commit sensitive credentials to the repository. Use `.env` files (gitignored) for local development and GitHub Secrets for CI/CD:

- `MISTRAL_API_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `SMTP_PASSWORD`
- `SENDGRID_API_KEY`
- `MAILGUN_API_KEY`
- `GITHUB_TOKEN` (provided by GitHub Actions, never hardcode)

### API Keys in Logs

The codebase currently uses `print()` statements that may leak API request details. Migration to proper logging with sensitive data redaction is in progress.

---

## Dependency Security

### Keeping Dependencies Updated

Run these commands regularly to check for security vulnerabilities:

```bash
pip install --upgrade pip-audit
pip-audit
```

### Current Pinned Versions

See `requirements.txt` for specific version pins. Major security updates should be tested in a development environment before deployment.

---

## GitHub Actions Security

### Secrets Management

All secrets are stored in GitHub repository settings under **Settings → Secrets and variables → Actions**.

Current secrets in use:
- `MISTRAL_API_KEY` - AI provider for OCR and summaries
- `GEMINI_API_KEY` - AI provider fallback
- `OPENAI_API_KEY` - AI provider final fallback
- Email provider secrets (SMTP/SendGrid/Mailgun)

### Workflow Permissions

Workflows use principle of least privilege:
- Harvest workflow: `contents: write`, `issues: write`
- OCR workflow: `contents: write`
- Release workflow: `contents: write` (when restored)

---

## Contact

For security concerns, contact the [Raphoe-Diocese](https://github.com/Raphoe-Diocese) org on GitHub. Do not open a public issue.

Last updated: 13/09/2026
