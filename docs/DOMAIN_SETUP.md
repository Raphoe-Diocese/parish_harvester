# Custom domain — `www.parishpress.ie`

This repo's GitHub Pages site is served at `www.parishpress.ie` (this superseded
an older `bulletins.parishpress.net` plan — that DNS record is no longer used
by this repo; `docs/CNAME` was updated to match on 2026-08-11).

## Step 1 — DNS records at the registrar for `parishpress.ie`

- **`www` CNAME** → `raphoe-diocese.github.io`
- **Apex `parishpress.ie` A records** → GitHub Pages IPs
  (`185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`)

Both of these are already correctly set (verified via `dig`, 2026-08-11).
No CAA record blocks Let's Encrypt — the apex has no CAA record at all, and
`www` (via its CNAME) inherits GitHub's own CAA records, which already allow
`letsencrypt.org`.

## Step 2 — Confirm in GitHub Pages settings

Open:
`https://github.com/Raphoe-Diocese/parish_harvester/settings/pages`

Check that **Custom domain** shows `www.parishpress.ie`.

## Known issue (as of 2026-08-11): HTTPS certificate stuck / not provisioned

`http://www.parishpress.ie` works, but `https://www.parishpress.ie` serves
GitHub's generic `*.github.io` wildcard certificate instead of a dedicated
certificate for `www.parishpress.ie` (confirmed with `openssl s_client`).
`GET /repos/.../pages` shows `https_enforced: false` and no
`https_certificate` object at all — GitHub has not (yet) successfully
provisioned a certificate for this domain. DNS and CAA are not the blocker.

**Next step (needs a repo admin — the agent's read-only GitHub token cannot
do this):**

1. Go to Settings → Pages.
2. Clear the **Custom domain** field and **Save**.
3. Wait ~30–60 seconds.
4. Re-enter `www.parishpress.ie` and **Save** again.
5. Watch for a green "DNS check successful" message, then tick
   **Enforce HTTPS** once it becomes available.
6. While there, read any error banner GitHub shows on that page — it isn't
   visible through the API and may explain the original failure directly
   (e.g. a domain-already-in-use conflict).

This remove-and-re-add cycle forces GitHub to redo the domain check and
restart Let's Encrypt certificate issuance. It can take anywhere from a few
minutes up to 24 hours after that to finish provisioning.

---

## Important note

`parishpress.ie` already redirects to `parishpress.net`. That is unrelated to
`www.parishpress.ie` (a distinct hostname) and needs no changes.
