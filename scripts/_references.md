# References Catalog — for in-moment lookup via research subagent

**Principle:** do not preload into context. When Claude is stuck on a specific vulnerability in `/hunt`, it dispatches a research subagent with a specific URL from here. The subagent reads the page and returns actionable steps.

**How to use in a skill:**
```
When unsure about exploitation:
1. Find the category below
2. Take the top URL for that category
3. Dispatch a research subagent with that URL
4. Get the methodology / payloads
```

---

## Top-3 universal references (read these first if you don't know where to go)

- **HackTricks** — https://book.hacktricks.xyz — the most complete bug bounty book, has everything
- **PortSwigger Web Security Academy** — https://portswigger.net/web-security — methodology + labs
- **PayloadsAllTheThings** — https://github.com/swisskyrepo/PayloadsAllTheThings — payload database

---

## Web2 — by category

### XSS (Cross-Site Scripting)
- HackTricks XSS — https://book.hacktricks.xyz/pentesting-web/xss-cross-site-scripting
- PayloadsAllTheThings XSS — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/XSS%20Injection
- PortSwigger XSS Academy — https://portswigger.net/web-security/cross-site-scripting
- XSS Cheatsheet by PortSwigger — https://portswigger.net/web-security/cross-site-scripting/cheat-sheet
- kxss (quiet reflection check) — https://github.com/Emoe/kxss — checks reflection of `<>"'` WITHOUT intrusive payloads → fewer WAF triggers, fast pre-filter before a full XSS test. Aligns with our WAF-safe philosophy ([[feedback_waf_safe_reports]]). For /dapphunt on dApp front-end parameters.

### SQL Injection
- HackTricks SQLi — https://book.hacktricks.xyz/pentesting-web/sql-injection
- PayloadsAllTheThings SQL — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/SQL%20Injection
- PortSwigger SQLi Academy — https://portswigger.net/web-security/sql-injection

### SSRF (Server-Side Request Forgery)
- HackTricks SSRF — https://book.hacktricks.xyz/pentesting-web/ssrf-server-side-request-forgery
- PayloadsAllTheThings SSRF — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/Server%20Side%20Request%20Forgery
- Cloud metadata endpoints (AWS/GCP/Azure) — https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/Server%20Side%20Request%20Forgery/README.md#bypass-using-host-header
- interactsh (OOB collaborator, self-host) — https://github.com/projectdiscovery/interactsh — for blind SSRF/XSS/XXE PoC when egress is filtered and the response is not visible (e.g. an egress-filtered SSRF where an OOB channel would prove reachability). Open-source Burp Collaborator.

### IDOR (Insecure Direct Object Reference)
- HackTricks IDOR — https://book.hacktricks.xyz/pentesting-web/idor
- PortSwigger Access Control Academy — https://portswigger.net/web-security/access-control

### Authentication & OAuth
- HackTricks OAuth — https://book.hacktricks.xyz/pentesting-web/oauth-to-account-takeover
- PortSwigger OAuth Academy — https://portswigger.net/web-security/oauth
- JWT attacks — https://book.hacktricks.xyz/pentesting-web/hacking-jwt-json-web-tokens
- PayloadsAllTheThings JWT — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/JSON%20Web%20Token

### XXE (XML External Entity)
- HackTricks XXE — https://book.hacktricks.xyz/pentesting-web/xxe-xee-xml-external-entity
- PayloadsAllTheThings XXE — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/XXE%20Injection

### SSTI (Server-Side Template Injection)
- HackTricks SSTI — https://book.hacktricks.xyz/pentesting-web/ssti-server-side-template-injection
- PayloadsAllTheThings SSTI — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/Server%20Side%20Template%20Injection

### CORS Misconfiguration
- PortSwigger CORS — https://portswigger.net/web-security/cors
- HackTricks CORS — https://book.hacktricks.xyz/pentesting-web/cors-bypass

### Open Redirect
- PayloadsAllTheThings Open Redirect — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/Open%20Redirect

### Subdomain Takeover
- EdOverflow can-i-take-over-xyz — https://github.com/EdOverflow/can-i-take-over-xyz
- HackTricks Domain Takeover — https://book.hacktricks.xyz/network-services-pentesting/pentesting-web/dns-vulnerabilities

### File Upload
- HackTricks File Upload — https://book.hacktricks.xyz/pentesting-web/file-upload
- PayloadsAllTheThings File Upload — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/Upload%20Insecure%20Files

### GraphQL
- HackTricks GraphQL — https://book.hacktricks.xyz/network-services-pentesting/pentesting-web/graphql
- (our `scripts/graphql_advanced.py` already covers batching/alias/depth/field-suggest/CSRF/authz-bypass)
- clairvoyance (schema reconstruction with introspection DISABLED, via a field-suggestion oracle) — https://github.com/nikitastupin/clairvoyance — the one thing our script lacks: reconstructing the schema when introspection is blocked in prod (a common case with DeFi-dashboard GraphQL)

### 403 / 401 Bypass
- PayloadsAllTheThings 401-403 Bypass — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/403%20Bypass

### Race Conditions
- PortSwigger Race Conditions — https://portswigger.net/web-security/race-conditions

### HTTP Request Smuggling
- PortSwigger Request Smuggling — https://portswigger.net/web-security/request-smuggling

### Recon methodology
- HackTricks Recon — https://book.hacktricks.xyz/generic-methodologies-and-resources/external-recon-methodology

### Niche tools (outside the Docker bbt image; added from awesome-bugbounty-tools 2026-06-14, dedup done)
Most of awesome-bugbounty-tools duplicates our /hunt + Docker bbt + dapphunt. What is genuinely new are these 4
plus 2 already in the SSRF/GraphQL sections (interactsh, clairvoyance):
- jsluice (AST parsing of JS, not regex) — https://github.com/BishopFox/jsluice — more precise than `js_mining.py` (regex+linkfinder) on minified dApp bundles: extracts URLs/paths/secrets/provider app-IDs (Privy/Dynamic) from the AST. Optionally wire a subprocess into js_mining.py as already done with secretfinder.
- keyhacks (validation of discovered API keys) — https://github.com/streaak/keyhacks — post-find: found a leaked Infura/Alchemy/Etherscan key → how to check it is live without extra requests. → post_find phase.
- zizmor (static analysis of GitHub Actions) — https://github.com/woodruffw/zizmor — web3 projects deploy contracts via GH Actions → CI/CD supply-chain (poisoned workflow → malicious deploy). Run it against the target's public `.github/workflows/` during recon. Niche, but a class we don't cover.
- domdig (DOM-XSS for SPAs, dynamic) — https://github.com/fcavallarin/domdig — complements our static `wallet_metadata_xss_check.py` with runtime coverage for SPA dApps (on-chain metadata → innerHTML sink class). Optional, when the static check gives a candidate but you need a live PoC.
- page-fetch (render SPA + arbitrary JS to harvest routes/links) — https://github.com/detectify/page-fetch — `--javascript '[...document.querySelectorAll("a")].map(n=>n.href)'`; extracts routes that appear only after the React render (static js_mining does not see them). For /dapphunt endpoint discovery on SPA dApps.
- (added from KingOfBugBountyTips 2026-06-14): kxss → XSS section; passive subdomain source JLDC/Anubis `curl -s https://jldc.me/anubis/subdomains/TARGET` — a separate DB, does not overlap with crt.sh/Chaos, +coverage in /hunt recon.
- SKIP (we have deeper/duplicate): inql (→graphql_advanced.py); SecretFinder/js-snitch/cariddi (→js_mining.py); postMessage-tracker/tracy (→postmessage_audit.py); csprecon/github-subdomains/mass subdomain-enum (→/hunt recon); **certstream** (→`dapphunt/monitors/dapp_clone_spawn_monitor.py` already does polling-CT + diff + framing-probe = equivalent, the latency is not critical); GraphQL 166-path nuclei-template (→graphql_advanced.py tests the endpoint more deeply; a discovery path list is not needed separately). All port-scan/sqlmap/brute-force/CMS/bucket — Docker bbt or forbidden by policy.
- ProjectDiscovery best practices — https://docs.projectdiscovery.io

---

## Web3 — by category

### General / methodology
- SWC Registry — https://swcregistry.io — the standard for IDs of smart contract weaknesses
- Solodit — https://solodit.cyfrin.io — search over historical audit findings (great for patterns)
- Solidity Patterns — https://github.com/fravoll/solidity-patterns
- Cyfrin Updraft — https://updraft.cyfrin.io
- Sigp Solidity Security Blog — https://github.com/sigp/solidity-security-blog
- Immunefi Top 10 — https://immunefi.com/immunefi-top-10/
- DeFi Security Summit talks — https://defisecuritysummit.org

### Reentrancy
- Damn Vulnerable DeFi solutions (after completing it) — https://github.com/theredguild/damn-vulnerable-defi
- ConsenSys Reentrancy guide — https://consensys.github.io/smart-contract-best-practices/attacks/reentrancy/

### Access Control
- OpenZeppelin AccessControl docs — https://docs.openzeppelin.com/contracts/5.x/access-control

### Oracle Manipulation
- Euler Finance hack analysis — https://www.iosiro.com/blog/euler-finance-exploit-postmortem
- Chainlink security best practices — https://docs.chain.link/data-feeds/selecting-data-feeds#getting-started

### Flash Loans
- Damn Vulnerable DeFi flash loan challenges
- Aave Flash Loans best practices — https://docs.aave.com/developers/guides/flash-loans

### Bridge / Cross-chain
- LayerZero security docs — https://docs.layerzero.network/v2/developers/evm/configuration/dvn-executor-config
- Wormhole hack analysis (to understand the pattern) — https://blog.chainalysis.com/reports/wormhole-hack-february-2022/

### MEV / Front-running
- Flashbots docs — https://docs.flashbots.net
- HackTricks MEV — there is a section in the Web3 part

### Solana (for a future phase)
- Sec3 Audit DB — https://www.sec3.dev/audits
- Anchor security — https://book.anchor-lang.com/anchor_in_depth/the_program_module.html
- Solana cookbook — https://solanacookbook.com

---

## E-commerce / Payment specific

- PCI DSS quick reference — https://www.pcisecuritystandards.org/document_library
- Magecart attack patterns — https://blog.sansec.io/  
- HackTricks Payment — https://book.hacktricks.xyz/pentesting-web/payment-process

---

## Disclosure / Communication

- security.txt spec — https://securitytxt.org
- VRT (Bugcrowd Vulnerability Rating Taxonomy) — https://bugcrowd.com/vulnerability-rating-taxonomy
- HackerOne disclosure guidelines — https://docs.hackerone.com/programs/program-management.html
- Immunefi V2.3 severity — https://immunefi.com/immunefi-vulnerability-severity-classification-system-v2-3/

---

## Recent vulnerabilities (CVE / live monitoring)

- CVE database — https://www.cve.org
- Nuclei templates index — https://nuclei.projectdiscovery.io/templates-overview/
- Sploitus aggregator — https://sploitus.com — Exploit-DB + GitHub PoC

---

## Practice / Training (for skill development, not in-moment)

- HackTheBox — https://app.hackthebox.com
- TryHackMe — https://tryhackme.com
- PortSwigger Web Security Academy — https://portswigger.net/web-security (free, gold)
- PentesterLab — https://pentesterlab.com
- Ethernaut — https://ethernaut.openzeppelin.com (Solidity)
- Capture The Ether — https://capturetheether.com (Solidity)
- Paradigm CTF — https://ctf.paradigm.xyz (Web3)
- Sec3 Solana CTF — https://www.sec3.dev/learn

---

## Research blogs (for long-term tracking)

### Web2
- PortSwigger Research — https://portswigger.net/research (top 10 web hacking techniques of the year)
- Intigriti blog — https://blog.intigriti.com
- HackerOne Hacktivity — https://hackerone.com/hacktivity (public disclosed reports)

### Web3
- Trail of Bits — https://blog.trailofbits.com
- OpenZeppelin — https://blog.openzeppelin.com
- ConsenSys Diligence — https://consensys.io/diligence/blog
- a16z Crypto — https://a16zcrypto.com/posts/
- Paradigm Research — https://www.paradigm.xyz/writing
- Blockaid — https://www.blockaid.io/blog
- rekt.news — https://rekt.news
- DefiYield Rekt DB — https://defiyield.app/rekt-database
