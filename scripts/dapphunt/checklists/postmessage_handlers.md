# postMessage handler audit — checklist

## 1. Find every handler

- [ ] Run `core/postmessage_audit.py --target $DOMAIN`
- [ ] Grep `window.addEventListener('message'` AND `onmessage` AND `addEventListener("message"`
- [ ] Note iframe boundaries — handlers on parent vs child have different threat models

## 2. Classify origin validation per handler

| Pattern | Risk |
|---|---|
| `e.origin === EXPECTED` | OK (strict) |
| `[allowlist].includes(e.origin)` | OK if allowlist is hardcoded literal |
| `e.origin.includes('trusted')` | BYPASSABLE via `trusted.attacker.com` |
| `e.origin.endsWith('.trusted')` | BYPASSABLE via `e-trusted` look-alike |
| `e.origin.match(/regex/)` | Often broken — must anchor `^...$` |
| no check at all | CRITICAL — any cross-origin frame can drive |

## 3. Source vs origin

- [ ] `event.origin` = the origin string
- [ ] `event.source` = the actual window reference
- [ ] Strong handlers verify BOTH: origin string AND that source matches an expected iframe ref

## 4. Data parsing

- [ ] What does `event.data` flow into?
- [ ] `JSON.parse(event.data)` — safe if shape-validated; risky if not
- [ ] `eval(event.data)` — critical RCE primitive
- [ ] `new Function(event.data)` — critical
- [ ] React state update — XSS if data not sanitized before render
- [ ] Wallet method call — if attacker can post a fake `{type: 'sign', payload: 'X'}` and dApp signs without prompt = critical

## 5. PoC for substring bypass

```html
<!-- Attacker page on `trusted.com.attacker.com` (no real DNS needed if testing locally) -->
<iframe src="https://VICTIM_DAPP" id="t"></iframe>
<script>
  document.getElementById('t').onload = () => {
    document.getElementById('t').contentWindow.postMessage({type:'X', payload:'Y'}, '*');
  };
</script>
```

## 6. Common dApp postMessage patterns

- WalletConnect bridge messages
- Iframe wallet popups (Magic, Privy)
- DEX aggregator iframes (1inch, Matcha)
- Onramp widgets (Transak, MoonPay)
- TradingView widget bridge messages

Each is a candidate handler — verify origin check.

## Severity

- **Critical**: no origin check + sensitive action driven by data
- **High**: substring/regex check + sensitive action
- **Medium**: weak check + non-critical action
- **Low**: weak check + read-only / display-only action
