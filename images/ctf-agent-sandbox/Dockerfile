FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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
