# Console sessions are separate from access tokens

The console logs in with an admin password and gets an HttpOnly, SameSite=Strict session cookie; agents, the CLI and MCP keep using Bearer access tokens. Administrative endpoints (settings, providers, tokens, password, restart) accept only a console session, so a leaked agent token can read and write memories but cannot change provider keys or lock the owner out. This replaces the web console's first design (#6), which kept the access token in `sessionStorage` and sent it as Bearer: that put the strongest credential in the browser, where one HTML injection would expose it.

## Consequences

- The console needs CSRF protection (SameSite=Strict plus an Origin check on state-changing requests).
- The token from the configuration file only bootstraps the console: it can log in until an admin password exists, then it cannot.
- Login has no rate limit or lockout by the owner's decision; password strength is the only defence. A Cloudflare rate rule on the login path is the fallback if that changes.
