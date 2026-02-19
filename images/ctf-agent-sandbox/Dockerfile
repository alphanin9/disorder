FROM python:3.11-slim-bookworm

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
    cpio \
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
    ripgrep \
    sagemath \
    socat \
    strace \
    unzip \
    vim-common \
    wget \
    zip

# Setup Dotnet SDK for ilspycmd
RUN wget https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -O packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    rm packages-microsoft-prod.deb && \
    apt-get update && \
    apt-get install -y \
    dotnet-sdk-8.0 \
    dotnet-sdk-10.0 && \
    rm -rf /var/lib/apt/lists/*

RUN dotnet tool install ilspycmd

RUN pip install --no-cache-dir \
    https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip \
    idapro \
    libdebug \
    numpy \
    pwntools \
    pycryptodome \
    ropper \
    sympy \
    uv \
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

# Note: apparently needed
RUN dotnet tool restore

ENTRYPOINT ["python", "/usr/local/bin/agent_runner.py"]
