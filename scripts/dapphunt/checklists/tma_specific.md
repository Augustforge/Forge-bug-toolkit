# Telegram Mini App (TMA) — checklist

TMA = Web app hosted by a Telegram bot, opened inside Telegram's WebView with
extra `Telegram.WebApp` API surface. SynFutures has a Telegram bot integration
making this relevant.

## initData validation

- [ ] Does the dApp validate `Telegram.WebApp.initData` server-side?
- [ ] Validation = HMAC-SHA256 over initData query string using bot token
- [ ] Frontend `Telegram.WebApp.initDataUnsafe` is **NOT** authenticated — never trust it
- [ ] Run `tma/tma_initdata_audit.py` to flag

## auth_date freshness

- [ ] Server enforces `auth_date` < 5 minutes old?
- [ ] If unbounded → indefinite replay window

## Bot token leak

- [ ] Bot token shape: `\d{8,10}:[A-Za-z0-9_-]{30,}`
- [ ] Should NEVER appear in frontend bundle
- [ ] If present → critical: anyone with token can send messages as the bot, intercept user data

## Cross-bot replay

- [ ] If same initData is accepted across multiple bots in the same family → bot impersonation
- [ ] HMAC must bind to bot ID

## Sandbox API misuse

- [ ] `Telegram.WebApp.BiometricManager.authenticate()` — UX hint only, NOT proof
- [ ] `Telegram.WebApp.showPopup({title, ...})` — title rendering: sanitized?
- [ ] `Telegram.WebApp.openLink(url)` — URL validated? open-redirect risk
- [ ] `Telegram.WebApp.openTelegramLink(url)` — `tg://` URI injection
- [ ] `Telegram.WebApp.themeParams.X` — used in inline CSS? CSS injection vector
- [ ] `Telegram.WebApp.requestContact` — returns user phone, store responsibly
- [ ] `Telegram.WebApp.CloudStorage` — per-key size limit; quota errors?
- [ ] `Telegram.WebApp.MainButton.setText` — race conditions if changed rapidly?

Run `tma/tma_sandbox_probe.py` to enumerate API usage.

## Wallet integration in TMA

- [ ] TMA usually uses WalletConnect or in-app wallet
- [ ] When user signs, what does TMA display? Native Telegram UI? Embedded webview?
- [ ] Test cross-chain: EVM + Solana + TON support varies per TMA

## TON-specific (if applicable)

- [ ] TON Connect URI handling
- [ ] tonkeeper-style deeplink behavior

## Severity

- **Critical**: bot token leak in frontend → bot impersonation, message interception
- **High**: initData not validated server-side → user impersonation in dApp
- **Medium**: auth_date not checked → replay window
- **Low**: API misuse (popup title XSS, theme injection)

## Reference

- Telegram official: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
