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
      socat \
      strace \
      unzip \
      vim-common \
      wget \
      zip && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      pwntools \
      pycryptodome \
      ropper \
      z3-solver && \
    npm install -g @openai/codex

RUN useradd -m -u 1000 -s /bin/bash ctf && \
    mkdir -p /workspace/chal /workspace/run /home/ctf/.codex && \
    chown -R ctf:ctf /workspace /home/ctf

WORKDIR /workspace

COPY agent_runner.py /usr/local/bin/agent_runner.py
COPY flag_verify_mcp.py /usr/local/bin/flag_verify_mcp.py
COPY agent_prompt.txt /usr/local/share/agent_prompt.txt
COPY ctf_tooling_guide.md /usr/local/share/ctf_tooling_guide.md

RUN chmod +x /usr/local/bin/agent_runner.py /usr/local/bin/flag_verify_mcp.py

USER ctf

ENTRYPOINT ["python", "/usr/local/bin/agent_runner.py"]
