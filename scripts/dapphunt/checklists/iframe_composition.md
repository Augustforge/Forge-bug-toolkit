# Iframe trust composition — checklist

For each public host the target ships content on:

## 1. Headers per host

- [ ] `X-Frame-Options` — DENY / SAMEORIGIN / wildcard / absent
- [ ] `Content-Security-Policy` directive `frame-ancestors` — 'none' / 'self' / explicit list / wildcard / absent
- [ ] When both X-Frame-Options and CSP frame-ancestors disagree, modern browsers prefer CSP — but Safari historically used the weaker policy. Note any disagreement.

## 2. Cross-host comparison

- [ ] Identify every host that ships the dApp bundle (use `dapp_clone_detector.py`)
- [ ] For each: are headers consistent with primary host?
- [ ] If primary = strict (DENY/'none') AND any clone = absent/wildcard → finding

## 3. Auth iframe layer

- [ ] What's the auth provider iframe URL? (e.g. https://auth.privy.io/, https://auth.magic.link/)
- [ ] What does its CSP `frame-ancestors` allow?
- [ ] If allow list includes wildcards: any host under the wildcard that's compromised = wallet phishing primitive

## 4. Multi-layer iframe chains

- [ ] dApp embeds wallet iframe?
- [ ] Wallet iframe embeds Privy iframe?
- [ ] Each layer needs strict frame-ancestors — weakest link wins

## 5. PoC builder

Minimum demonstration HTML:

```html
<!DOCTYPE html>
<html>
<head><title>Iframe composition PoC</title></head>
<body>
  <iframe src="https://CLONE_HOST_WITHOUT_HEADERS/" width="1280" height="800"></iframe>
  <!-- if this iframe renders the dApp UI, finding is confirmed -->
</body>
</html>
```

Serve from a local HTTP server (not file://) and open in 3 browsers: Chrome, Firefox, Safari.

## 6. Composition with overlay

For a full Clickjacking demo (not required for technical validity but boosts severity):

```html
<style>
  .overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%;
             background: rgba(0,0,0,0); pointer-events: none; }
  .lure-button { position: absolute; top: 600px; left: 400px; pointer-events: auto;
                 background: rgba(0,255,0,0); color: rgba(0,0,0,0); }
</style>
<div class="overlay">
  <button class="lure-button">Claim Reward</button>
</div>
```

Position the lure-button directly over the iframe's "Connect Wallet" / "Approve" button location.

## Severity calibration

- **High**: clone exists + wildcard auth trust + clickjacking PoC works
- **Medium**: clone exists + missing headers but no auth trust composition
- **Low**: framing class possible but no composability with wallet flow
