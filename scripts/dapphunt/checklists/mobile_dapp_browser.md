# Mobile in-app browser — checklist

MetaMask Mobile, Trust Wallet, Rainbow, Phantom (mobile) embed a WebView that
runs the dApp. The threat model is subtly different from desktop browsers.

## Sandbox differences

- [ ] In-app WebView usually doesn't honor all desktop CSP directives identically
- [ ] iOS WKWebView vs Android WebView vs Chrome WebView — three different engines
- [ ] Cookies may be shared across in-app sessions for the same wallet app
- [ ] `window.opener` behavior differs

## Universal links / App Links

- [ ] dApp uses universal links (iOS) / app links (Android)?
- [ ] Conflict with other apps claiming the same URL path?
- [ ] If attacker controls a competing app on user's device, user could be routed there
- [ ] Test: install both apps, see which wins

## Deeplink handling

- [ ] dApp accepts `wc:?...` WalletConnect URIs?
- [ ] dApp accepts `ethereum:address?value=...` URIs?
- [ ] Solana `solana:...` URIs?
- [ ] Each is a potential injection vector if dApp opens them without parsing safely

## In-app vs external opening

- [ ] What does dApp do when user clicks a link inside the in-app browser?
- [ ] Opens in same WebView (security context inherited)?
- [ ] Opens in system browser (escapes WebView trust)?
- [ ] Either choice has implications — document which the dApp uses

## Origin confusion

- [ ] In-app browsers may inject `window.ethereum` (or `window.solana`) directly
- [ ] dApp may assume the injected provider is the in-app wallet — but other apps can also inject
- [ ] Race: multiple providers, ordering decides which gets used
- [ ] Mobile in-app provider may not respect EIP-6963 multi-provider standard

## Biometric trust (Telegram, but also wallet apps)

- [ ] Wallet app prompts for biometric to sign?
- [ ] Biometric is local-only — not cryptographic proof to the dApp
- [ ] If dApp displays "biometric verified" as if it's strong auth, that's misleading

## Testing approach

- [ ] Real device or emulator with the wallet app installed
- [ ] Connect Reactotron / mobile DevTools for WebView debugging
- [ ] Capture EIP-1193 calls from in-app provider via mock injection (where supported)
- [ ] Compare in-app behavior to desktop browser behavior — log differences

## Severity

- **High**: dApp behaves differently in-app such that an attacker gets a primitive (e.g. signature accepted with no UI)
- **Medium**: deeplink mishandled, opens unexpected target
- **Low**: UI inconsistency in mobile WebView (informational)
