# Custom Nuclei Templates

Templates specific to bug bounty hunting. They complement the stock nuclei-templates for:
- Fresh CVEs not yet in the stock pool
- A specific company watchlist
- Threat-intel patterns (frontend hijack indicators, exposed admin)

Run:
```bash
nuclei -t /path/to/nuclei-templates -t /path/to/nuclei-templates-custom/ -u TARGET
```

In `scan.sh` this is already wired in via the `-t` flag.

## Structure

```
nuclei-templates-custom/
├── exposed/         # exposed admin panels, dashboards, configs
├── web3/            # Web3-specific (DeFi UI, weak CSP on dApps)
├── recent-cve/      # fresh CVEs
└── company-specific/ # for a specific company watchlist
```

## How to write a template

See https://docs.projectdiscovery.io/templates/introduction for the documentation.

## Sources of ready-made templates

- https://github.com/projectdiscovery/nuclei-templates (main)
- https://github.com/geeknik/the-nuclei-templates (community)
- https://github.com/pikpikcu/nuclei-templates (custom)
- https://github.com/0x727/Nuclei-templates-cn (China-focused)
