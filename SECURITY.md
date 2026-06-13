# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it by:

1. **DO NOT** open a public GitHub issue
2. Email the repository owner directly through their GitHub profile
3. Include detailed information about the vulnerability and steps to reproduce

We will respond within 48 hours and work with you to address the issue.

---

## Known Security Issues

### ⚠️ CRITICAL: Chrome Extension Private Key Exposed

**Issue**: The Chrome extension private key is currently embedded in `extension/manifest.json` (line 35+).

**Risk**: Anyone with access to this key can publish malicious updates to the extension under the same extension ID.

**Status**: Known issue. Private repositories only.

**Mitigation Steps Required**:

1. **Remove the `"key"` field** from `extension/manifest.json`
2. **Store the key securely**:
   - Save the private key file (`.pem`) to a secure location outside the repository
   - Add the key file to `.gitignore` (already done)
   - For GitHub Actions, store the key in GitHub Secrets as `CHROME_EXTENSION_KEY`
3. **Update the release workflow** to inject the key at build time:
   ```yaml
   - name: Add extension key
     run: |
       echo '${{ secrets.CHROME_EXTENSION_KEY }}' > extension.pem
       # Update manifest.json to include key reference
   ```
4. **Rotate the extension ID** if this key has been compromised (requires republishing to Chrome Web Store)

### Temporary Workaround

Until the above steps are completed:
- Keep the repository **private**
- Do not share the extension package publicly
- Audit repository access regularly

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

For security concerns, contact [@Frankytyrone](https://github.com/Frankytyrone) via GitHub.

Last updated: June 2, 2026
