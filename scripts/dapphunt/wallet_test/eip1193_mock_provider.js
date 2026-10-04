// eip1193_mock_provider.js — Inject a mock EIP-1193 wallet into a page for
// safe, observable testing without a real wallet.
//
// Usage:
//   1) Inject via DevTools Protocol or `--init-script` in a browser instrumentation tool.
//   2) The mock logs every method called and the parameters to console.
//   3) Override RESPONSE_TABLE below to control what the dApp sees back.
//
// What this lets you observe:
//   - Exact `request({ method, params })` calls a dApp makes
//   - EIP-712 typed-data payloads (look at `eth_signTypedData_v4` params)
//   - The order of `eth_requestAccounts` → `wallet_switchEthereumChain` → tx
//   - Whether the dApp checks chainId before signing
//
// IMPORTANT: this is an analysis tool, not an attack tool. Use only on
// dApps you have authorization to test (in-scope bounty programs).

(function injectMock() {
  const BURNER_ADDRESS = "0x000000000000000000000000000000000000dEaD";

  // Injectable config (e.g. via Playwright addInitScript BEFORE this script:
  // window.__MOCK_CONFIG__ = { isMetaMask: false }). Default preserves old behavior.
  // see runtime_harness.py
  const MOCK_CONFIG = (typeof window !== "undefined" && window.__MOCK_CONFIG__) || {};

  // Override per-test as needed
  const RESPONSE_TABLE = {
    eth_accounts: [BURNER_ADDRESS],
    eth_requestAccounts: [BURNER_ADDRESS],
    eth_chainId: "0x2105", // Base mainnet by default
    net_version: "8453",
    eth_blockNumber: "0x10000000",
    eth_getBalance: "0x6f05b59d3b20000", // 0.5 ETH-ish in wei
    wallet_getPermissions: [
      {
        invoker: "https://example",
        parentCapability: "eth_accounts",
        caveats: [{ type: "restrictReturnedAccounts", value: [BURNER_ADDRESS] }],
      },
    ],
    // Pre-signed VALID burner signatures for signature-class requests (personal_sign /
    // eth_sign / eth_signTypedData*), keyed by method name OR by the raw typed-data JSON
    // string / message the dApp passes as a param (see _lookupSignature below). Populated
    // by the harness from `onchain_poc_harness.py sign-typed-data` output (no broadcast).
    // see runtime_harness.py
    signatures: {},
  };

  // Track every call for post-test analysis
  const callLog = [];

  // Look up a pre-signed VALID burner signature for a signature-class request: by method
  // name first, then by any string param (covers the typed-data JSON / message payload used
  // as the registration key). Returns null if nothing was pre-signed -- caller falls back to
  // the old fake signature. see runtime_harness.py
  function _lookupSignature(method, params) {
    const sigTable = RESPONSE_TABLE.signatures || {};
    if (sigTable[method] !== undefined) return sigTable[method];
    try {
      if (Array.isArray(params)) {
        for (const p of params) {
          if (typeof p === "string" && sigTable[p] !== undefined) return sigTable[p];
        }
      }
      const paramsKey = JSON.stringify(params);
      if (sigTable[paramsKey] !== undefined) return sigTable[paramsKey];
    } catch (e) {
      // malformed params -- fall through, caller uses fake fallback
    }
    return null;
  }

  const provider = {
    isMetaMask: MOCK_CONFIG.isMetaMask !== undefined ? MOCK_CONFIG.isMetaMask : true,
    isConnected: () => true,
    chainId: RESPONSE_TABLE.eth_chainId,
    selectedAddress: BURNER_ADDRESS,
    networkVersion: RESPONSE_TABLE.net_version,

    request: async ({ method, params }) => {
      const entry = { ts: Date.now(), method, params };
      callLog.push(entry);
      console.log("[mock-eip1193]", method, params || "");

      if (method in RESPONSE_TABLE) {
        return RESPONSE_TABLE[method];
      }

      // Signature-class methods — return a pre-signed VALID burner signature if the harness
      // injected one for this request (RESPONSE_TABLE.signatures, see runtime_harness.py);
      // otherwise fall back to the old fake/invalid signature.
      if (method === "personal_sign" || method === "eth_sign" || method.startsWith("eth_signTypedData")) {
        console.warn("[mock-eip1193] SIGNATURE REQUESTED:", method, params);
        const preSigned = _lookupSignature(method, params);
        if (preSigned) {
          return preSigned;
        }
        console.warn("[mock] unsigned scenario -- no pre-signed signature in RESPONSE_TABLE.signatures, returning fake");
        return "0x" + "ab".repeat(65);
      }

      // Transaction-class — log and return fake tx hash
      if (method === "eth_sendTransaction" || method === "eth_sendRawTransaction") {
        console.warn("[mock-eip1193] TRANSACTION REQUESTED:", params);
        return "0x" + "cd".repeat(32);
      }

      // Chain switching
      if (method === "wallet_switchEthereumChain" || method === "wallet_addEthereumChain") {
        console.warn("[mock-eip1193] CHAIN SWITCH:", params);
        return null;
      }

      // Default: return undefined; observe whether dApp handles missing method
      console.warn("[mock-eip1193] UNHANDLED METHOD:", method);
      return undefined;
    },

    // Legacy EIP-1193 events
    on: (event, handler) => {
      console.log("[mock-eip1193] subscribe to", event);
    },
    removeListener: () => {},
    emit: () => {},

    // Expose call log for inspection
    __getCallLog: () => callLog,
    __clearCallLog: () => { callLog.length = 0; },
  };

  // Inject as `window.ethereum`
  Object.defineProperty(window, "ethereum", { value: provider, writable: false, configurable: true });

  // Also dispatch the `eip6963:announceProvider` events some dApps look for
  window.dispatchEvent(new CustomEvent("eip6963:announceProvider", {
    detail: {
      info: { uuid: "00000000-0000-0000-0000-000000000000", name: "Mock Wallet", icon: "", rdns: "io.dapphunt.mock" },
      provider,
    },
  }));

  console.log("[mock-eip1193] injected. window.ethereum.__getCallLog() shows requests.");
})();
