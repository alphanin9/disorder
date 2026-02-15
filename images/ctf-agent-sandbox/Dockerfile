FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG INSTALL_GHIDRA=1
ARG GHIDRA_VERSION=11.1.2

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      bash \
      binutils \
      build-essential \
      ca-certificates \
      curl \
      file \
      gdb \
      gdb-multiarch \
      git \
      jq \
      ltrace \
      netcat-openbsd \
      nodejs \
      npm \
      patchelf \
      p7zip-full \
      openjdk-21-jre-headless \
      ripgrep \
      socat \
      strace \
      unzip \
      vim-common \
      wget \
      zip && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      libdebug \
      pwntools \
      pycryptodome \
      ropper \
      sympy \
      pyghidra-mcp \
      z3-solver && \
    npm install -g @openai/codex

# micromamba is used by the crypto MCP to optionally bootstrap Sage into /workspace/run (on-demand).
RUN curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest | \
      tar -xvj -C /usr/local/bin --strip-components=1 bin/micromamba

# Optional: install Ghidra into the image (preferred for stable MCP startup).
# This increases image size substantially; disable in CI via build arg INSTALL_GHIDRA=0.
RUN if [ "${INSTALL_GHIDRA}" = "1" ]; then \
      set -eux; \
      apt-get update; \
      apt-get install -y --no-install-recommends findutils; \
      rm -rf /var/lib/apt/lists/*; \
      mkdir -p /opt/ghidra; \
      tag="Ghidra_${GHIDRA_VERSION}_build"; \
      api="https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/tags/${tag}"; \
      url="$(curl -fsSL -H 'User-Agent: ctf-harness' \"$api\" | jq -r '.assets[] | select(.name|test(\"ghidra_'\"${GHIDRA_VERSION}\"'_PUBLIC_.*\\\\.zip$\";\"i\")) | .browser_download_url' | head -n1)"; \
      if [ -z \"$url\" ] || [ \"$url\" = \"null\" ]; then \
        url="$(curl -fsSL -H 'User-Agent: ctf-harness' \"$api\" | jq -r '.assets[] | select(.name|endswith(\".zip\")) | .browser_download_url' | head -n1)"; \
      fi; \
      if [ -z \"$url\" ] || [ \"$url\" = \"null\" ]; then \
        echo \"failed to locate ghidra asset url via GitHub API for ${tag}\" >&2; \
        exit 2; \
      fi; \
      curl -fsSL -H 'User-Agent: ctf-harness' \"$url\" -o /tmp/ghidra.zip; \
      unzip -q /tmp/ghidra.zip -d /opt/ghidra; \
      rm /tmp/ghidra.zip; \
      ghdir=\"$(find /opt/ghidra -maxdepth 1 -mindepth 1 -type d | head -n1)\"; \
      if [ -z \"$ghdir\" ]; then echo \"ghidra extract failed\" >&2; exit 2; fi; \
      ln -s \"$ghdir\" /opt/ghidra/current; \
    fi

ENV GHIDRA_INSTALL_DIR=/opt/ghidra/current

RUN useradd -m -u 1000 -s /bin/bash ctf && \
    mkdir -p /workspace/chal /workspace/run /home/ctf/.codex && \
    chown -R ctf:ctf /workspace /home/ctf

WORKDIR /workspace

COPY agent_runner.py /usr/local/bin/agent_runner.py
COPY flag_verify_mcp.py /usr/local/bin/flag_verify_mcp.py
COPY crypto_math_mcp.py /usr/local/bin/crypto_math_mcp.py
COPY ghidra_mcp.py /usr/local/bin/ghidra_mcp.py
COPY ida_mcp.py /usr/local/bin/ida_mcp.py
COPY agent_prompt.txt /usr/local/share/agent_prompt.txt
COPY ctf_tooling_guide.md /usr/local/share/ctf_tooling_guide.md

RUN chmod +x /usr/local/bin/agent_runner.py /usr/local/bin/flag_verify_mcp.py /usr/local/bin/crypto_math_mcp.py /usr/local/bin/ghidra_mcp.py /usr/local/bin/ida_mcp.py

USER ctf

ENTRYPOINT ["python", "/usr/local/bin/agent_runner.py"]
