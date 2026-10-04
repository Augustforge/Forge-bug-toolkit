"""crt.sh subdomain enumeration — writes deduplicated subdomains to JSON."""
import sys, json, requests, time

def main(domain, output_dir):
    results = {"domain": domain, "subdomains": [], "error": None}
    try:
        r = requests.get(
            "https://crt.sh/",
            params={"q": f"%.{domain}", "output": "json"},
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0 (bug-bounty-research)"},
        )
        r.raise_for_status()
        data = r.json()
        subs = sorted({e["name_value"].strip().lower()
                       for e in data
                       if e.get("name_value") and domain in e["name_value"]})
        # expand wildcard entries
        cleaned = []
        for s in subs:
            for part in s.split("\n"):
                part = part.strip().lstrip("*.")
                if part and part.endswith(domain) and part not in cleaned:
                    cleaned.append(part)
        cleaned = sorted(set(cleaned))
        results["subdomains"] = cleaned
        results["count"] = len(cleaned)
        print(f"[crt.sh] {len(cleaned)} subdomains found for {domain}")
        for s in cleaned[:50]:
            print(f"  {s}")
        if len(cleaned) > 50:
            print(f"  ... and {len(cleaned)-50} more")
    except Exception as e:
        results["error"] = str(e)
        print(f"[crt.sh] ERROR: {e}", file=sys.stderr)

    import os
    out_path = os.path.join(output_dir, "crtsh_subdomains.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"[crt.sh] Saved to {out_path}")

if __name__ == "__main__":
    domain = sys.argv[1] if len(sys.argv) > 1 else "lightspark.com"
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    main(domain, out)
