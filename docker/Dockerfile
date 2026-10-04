FROM kalilinux/kali-rolling:latest

ENV DEBIAN_FRONTEND=noninteractive
ENV GO_VERSION=1.22.0
ENV PATH="/usr/local/go/bin:/root/go/bin:/root/.local/bin:${PATH}"

# Base deps
RUN apt-get update && apt-get install -y \
    curl wget git python3 python3-pip python3-venv \
    nmap masscan dnsutils whois \
    nikto sqlmap dirb gobuster \
    testssl.sh whatweb wafw00f \
    libpcap-dev build-essential \
    jq unzip nodejs npm \
    cppcheck clang clang-tidy bear \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Go
RUN wget -q https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz \
    && tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz \
    && rm go${GO_VERSION}.linux-amd64.tar.gz

# Go tools — each install in own RUN line with || true so a single failure doesn't kill build
RUN set -e; \
    for pkg in \
        github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest \
        github.com/projectdiscovery/httpx/cmd/httpx@latest \
        github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest \
        github.com/ffuf/ffuf/v2@latest \
        github.com/OJ/gobuster/v3@latest \
        github.com/hahwul/dalfox/v2@latest \
        github.com/tomnomnom/waybackurls@latest \
        github.com/tomnomnom/httprobe@latest \
        github.com/lc/gau/v2/cmd/gau@latest \
        github.com/hakluke/hakrawler@latest \
        github.com/projectdiscovery/dnsx/cmd/dnsx@latest \
        github.com/owasp-amass/amass/v4/...@latest \
        github.com/haccer/subjack@latest \
        github.com/ferreiraklet/Jeeves@latest \
        github.com/tomnomnom/assetfinder@latest \
        github.com/sw33tLie/bbscope@latest \
        github.com/michenriksen/aquatone@latest \
    ; do \
        echo "[+] go install $pkg"; \
        go install "$pkg" || echo "[!] FAILED: $pkg (skipped)"; \
    done

# Nuclei templates
RUN nuclei -update-templates -silent || true

# RustScan
RUN wget -q https://github.com/RustScan/RustScan/releases/download/2.3.0/rustscan_2.3.0_amd64.deb \
    && dpkg -i rustscan_2.3.0_amd64.deb \
    && rm rustscan_2.3.0_amd64.deb

# Python tools (including arjun — it is Python, not Go)
RUN pip3 install --break-system-packages \
    arjun \
    shodan \
    requests \
    curl_cffi \
    dnspython \
    boto3 \
    azure-storage-blob \
    google-cloud-storage \
    pyjwt \
    cryptography \
    beautifulsoup4 \
    lxml \
    colorama \
    rich \
    websockets \
    python-dotenv

# TruffleHog
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
    | sh -s -- -b /usr/local/bin

# Gitleaks
RUN wget -q https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_linux_x64.tar.gz \
    && tar -xzf gitleaks_8.18.4_linux_x64.tar.gz -C /usr/local/bin gitleaks \
    && rm gitleaks_8.18.4_linux_x64.tar.gz

# LinkFinder
RUN git clone --depth 1 https://github.com/GerbenJavado/LinkFinder.git /opt/linkfinder \
    && pip3 install --break-system-packages -r /opt/linkfinder/requirements.txt \
    && ln -s /opt/linkfinder/linkfinder.py /usr/local/bin/linkfinder

# SecretFinder
RUN git clone --depth 1 https://github.com/m4ll0k/SecretFinder.git /opt/secretfinder \
    && pip3 install --break-system-packages -r /opt/secretfinder/requirements.txt \
    && ln -s /opt/secretfinder/SecretFinder.py /usr/local/bin/secretfinder

# Commix
RUN git clone --depth 1 https://github.com/commixproject/commix.git /opt/commix \
    && ln -s /opt/commix/commix.py /usr/local/bin/commix

# wappalyzer CLI
RUN npm install -g wappalyzer-cli 2>/dev/null || true

# ─── WEB3 / SMART CONTRACT TOOLS ──────────────────────────────────────────────

# Python 3.10 isolated venv for Mythril (mythril does not support Python 3.11+)
RUN apt-get update && apt-get install -y python3.10 python3.10-venv python3.10-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/* || \
    (apt-get update && apt-get install -y software-properties-common && \
     add-apt-repository -y ppa:deadsnakes/ppa && apt-get update && \
     apt-get install -y python3.10 python3.10-venv python3.10-dev || true)

RUN python3.10 -m venv /opt/myth-venv 2>/dev/null && \
    /opt/myth-venv/bin/pip install --upgrade pip && \
    /opt/myth-venv/bin/pip install mythril && \
    ln -sf /opt/myth-venv/bin/myth /usr/local/bin/myth || \
    echo "[!] Mythril venv install skipped — Python 3.10 not available; use docker mythril/myth as fallback"

# Slither + crytic-compile + solc-select
RUN pip3 install --break-system-packages \
    slither-analyzer \
    solc-select \
    crytic-compile \
    eth-wake \
    semgrep

# Custom Slither detectors plugin (Immunefi Top 10 gaps + May 2026 attack patterns)
COPY scripts/web3/detectors /opt/bbt-detectors
RUN pip3 install --break-system-packages -e /opt/bbt-detectors || \
    echo "[!] Custom detectors plugin install skipped — see /opt/bbt-detectors/setup.py"

# solc versions (pre-fetch the popular ones)
RUN solc-select install 0.8.20 0.8.19 0.7.6 0.6.12 || true && \
    solc-select use 0.8.20 || true

# Foundry (forge / cast / anvil / chisel)
RUN curl -L https://foundry.paradigm.xyz | bash && \
    /root/.foundry/bin/foundryup
ENV PATH="/root/.foundry/bin:${PATH}"

# Rust toolchain (needed for Aderyn + Pyrometer)
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

# Aderyn — install via cargo (more reliable than a binary download — the release URL pattern changes)
RUN cargo install aderyn || echo "[!] Aderyn install failed — Web3 deep mode degraded"

# Echidna (property-based fuzzer)
RUN wget -q https://github.com/crytic/echidna/releases/download/v2.3.2/echidna-2.3.2-x86_64-linux.tar.gz \
    && tar -xzf echidna-2.3.2-x86_64-linux.tar.gz -C /usr/local/bin || \
    tar -xzf echidna-2.3.2-x86_64-linux.tar.gz -C /tmp && cp /tmp/echidna /usr/local/bin/ \
    ; rm -f echidna-2.3.2-x86_64-linux.tar.gz

# Halmos (a16z symbolic testing)
RUN pip3 install --break-system-packages halmos || \
    pip3 install --break-system-packages --user halmos || true

# 4naly3er (Code4rena gas + low-severity)
RUN git clone --depth 1 https://github.com/Picodes/4naly3er.git /opt/4naly3er && \
    cd /opt/4naly3er && yarn install 2>/dev/null || \
    (cd /opt/4naly3er && npm install) || \
    echo "[!] 4naly3er install skipped"

# Decurity Semgrep rules for smart contracts
RUN git clone --depth 1 https://github.com/Decurity/semgrep-smart-contracts.git \
    /opt/semgrep-smart-contracts || true

# Web3 Python SDK
RUN pip3 install --break-system-packages \
    web3 \
    eth-utils \
    eth-abi \
    py-solc-x \
    requests-cache \
    feedparser

# ─── ADDITIONAL TOOLS (extension v2) ──────────────────────────────────────────

# Tenderly CLI — transaction simulator + debugger (for verification PoC)
RUN curl -fsSL https://raw.githubusercontent.com/Tenderly/tenderly-cli/master/scripts/install-linux.sh \
    | sh 2>/dev/null || \
    npm install -g @tenderly/cli 2>/dev/null || \
    echo "[!] Tenderly CLI install skipped"

# interactsh-client — out-of-band testing for blind SSRF/XSS/RCE
RUN go install github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest

# notify — for push notifications (Telegram/Discord/Slack)
RUN go install github.com/projectdiscovery/notify/cmd/notify@latest

# chaos-client — bug bounty subdomain dataset from ProjectDiscovery
RUN go install github.com/projectdiscovery/chaos-client/cmd/chaos@latest

# mitmproxy — interactive API proxying
RUN pip3 install --break-system-packages mitmproxy

# OWASP ZAP CLI mode (free Burp alternative)
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jre wget unzip \
    && wget -q https://github.com/zaproxy/zaproxy/releases/download/v2.15.0/ZAP_2.15.0_Linux.tar.gz -O /tmp/zap.tar.gz \
    && tar -xzf /tmp/zap.tar.gz -C /opt/ \
    && ln -s /opt/ZAP_2.15.0/zap.sh /usr/local/bin/zap \
    && rm /tmp/zap.tar.gz \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    || echo "[!] ZAP install skipped"

# Pyrometer (Solidity range analyzer from Nascent)
RUN cargo install --git https://github.com/nascentxyz/pyrometer 2>/dev/null \
    || echo "[!] Pyrometer install skipped (cargo not be available)"

# SecLists — the gold standard of wordlists
RUN git clone --depth 1 https://github.com/danielmiessler/SecLists.git /opt/seclists \
    && echo "[+] SecLists cloned to /opt/seclists"

ENV SECLISTS=/opt/seclists

# ─── PHASE I.5 TOOLS ──────────────────────────────────────────────────────────

# katana — headless SPA crawling (finds hidden API endpoints via render)
RUN go install github.com/projectdiscovery/katana/cmd/katana@latest

# cloud_enum — multi-cloud OSINT (S3 / Azure Blob / GCP Buckets by keywords)
RUN git clone --depth 1 https://github.com/initstring/cloud_enum.git /opt/cloud_enum \
    && pip3 install --break-system-packages -r /opt/cloud_enum/requirements.txt \
    && ln -s /opt/cloud_enum/cloud_enum.py /usr/local/bin/cloud_enum \
    && chmod +x /usr/local/bin/cloud_enum

# jwt_tool — advanced JWT testing (alg confusion, KID injection, JWK)
RUN git clone --depth 1 https://github.com/ticarpi/jwt_tool.git /opt/jwt_tool \
    && pip3 install --break-system-packages -r /opt/jwt_tool/requirements.txt \
    && ln -s /opt/jwt_tool/jwt_tool.py /usr/local/bin/jwt_tool \
    && chmod +x /usr/local/bin/jwt_tool

# smuggler.py — HTTP/2 smuggling detection (PortSwigger)
RUN git clone --depth 1 https://github.com/defparam/smuggler.git /opt/smuggler \
    && ln -s /opt/smuggler/smuggler.py /usr/local/bin/smuggler

# h2cSmuggler — H2C smuggling
RUN git clone --depth 1 https://github.com/BishopFox/h2csmuggler.git /opt/h2csmuggler \
    || echo "[!] h2csmuggler clone skipped"

# ─── TON BLOCKCHAIN NODE ANALYSIS ────────────────────────────────────────────

# TON source — shallow clone for analysis of the C++ core
RUN git clone --depth 1 https://github.com/ton-blockchain/ton.git /opt/ton-src \
    || echo "[!] TON source clone skipped (will clone on-demand in scan.sh)"

# ─── SOLANA TOOLCHAIN (Phase K) ──────────────────────────────────────────────

# Build prereqs for the Rust/Solana toolchain (some needed for cargo install)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev pkg-config libudev-dev libclang-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    || echo "[!] Build prereqs install partial"

# Rust (prereq for Anchor + cargo tools) — confirm in one shell
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal \
    && . /root/.cargo/env \
    && /root/.cargo/bin/rustc --version \
    && /root/.cargo/bin/cargo --version
ENV PATH="/root/.cargo/bin:${PATH}"

# Solana CLI (release-stable) — Anza-hosted, requires non-tty fallback
RUN curl -sSfL https://release.anza.xyz/stable/install -o /tmp/solana-install.sh \
    && sh /tmp/solana-install.sh \
    && rm /tmp/solana-install.sh \
    && /root/.local/share/solana/install/active_release/bin/solana --version \
    || echo "[!] Solana CLI install FAILED — check Anza endpoint, network, glibc"
ENV PATH="/root/.local/share/solana/install/active_release/bin:${PATH}"

# Anchor CLI 0.31+ via AVM — needs Rust + Solana already PATH'd
RUN cargo install --git https://github.com/coral-xyz/anchor avm --force \
    && avm install 0.31.0 \
    && avm use 0.31.0 \
    && anchor --version \
    || echo "[!] Anchor install FAILED"

# Rust security tools — keep --locked for reproducibility, NO 2>/dev/null (we want errors visible)
RUN cargo install --locked cargo-audit || echo "[!] cargo-audit FAILED"
RUN cargo install --locked cargo-geiger || echo "[!] cargo-geiger FAILED"
RUN cargo install --locked cargo-deny || echo "[!] cargo-deny FAILED"

# LLVM (for sBPF disassembly via llvm-objdump --triple=bpf)
RUN apt-get update && apt-get install -y --no-install-recommends llvm clang lld \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && llvm-objdump --version | head -1 \
    || echo "[!] LLVM install FAILED"

# Sol-azy (FuzzingLabs 2025) — modular sBPF analyzer
RUN git clone --depth 1 https://github.com/FuzzingLabs/sol-azy.git /opt/sol-azy \
    && (cd /opt/sol-azy && cargo build --release && ln -sf /opt/sol-azy/target/release/sol-azy /usr/local/bin/sol-azy) \
    || echo "[!] Sol-azy install FAILED (network or compilation)"

# Ezbpf — simple sBPF disassembler
RUN cargo install --git https://github.com/deanmlittle/ezbpf \
    || echo "[!] ezbpf install FAILED"

# solders — Python binding for signing/serializing Solana tx (needed for the fork PoC harness)
RUN pip3 install --break-system-packages --no-warn-script-location --disable-pip-version-check solders \
    && python3 -c "import solders" \
    || echo "[!] solders install FAILED — exploit_harness.py --sign will not work"

# Trident — Ackee Blockchain Solana fuzzer v0.12+ (Phase S2 invariant break)
# 5-6 min compile, requires Rust+cargo
RUN cargo install trident-cli --version 0.12.0 --locked \
    && trident --version \
    || echo "[!] Trident install FAILED — Phase S2 fuzzing will be unavailable"

# Verify tools availability (non-blocking)
RUN echo "[+] Solana toolchain check:" \
    && (solana --version 2>/dev/null || echo "  solana: MISSING") \
    && (anchor --version 2>/dev/null || echo "  anchor: MISSING") \
    && (cargo audit --version 2>/dev/null || echo "  cargo-audit: MISSING") \
    && (llvm-objdump --version 2>/dev/null | head -1 || echo "  llvm-objdump: MISSING") \
    && (sol-azy --version 2>/dev/null || echo "  sol-azy: MISSING (fallback OK)") \
    && (python3 -c "import solders" 2>/dev/null && echo "  solders: OK" || echo "  solders: MISSING") \
    && (trident --version 2>/dev/null && echo "  trident: OK" || echo "  trident: MISSING") \
    && (x-ray --version 2>/dev/null || echo "  x-ray: MISSING (fallback OK)")

WORKDIR /workspace

CMD ["/bin/bash"]
