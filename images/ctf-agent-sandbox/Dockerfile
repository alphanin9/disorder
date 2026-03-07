FROM python:3.11-slim-bookworm AS sandbox-base

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    bash \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash ctf && \
    mkdir -p /workspace/chal /workspace/run /home/ctf/.codex && \
    chown -R ctf:ctf /workspace /home/ctf

WORKDIR /workspace

COPY agent_runner.py /usr/local/bin/agent_runner.py
COPY flag_verify_mcp.py /usr/local/bin/flag_verify_mcp.py
COPY flag_submit_mcp.py /usr/local/bin/flag_submit_mcp.py
COPY agent_prompt.txt /usr/local/share/agent_prompt.txt
COPY ctf_tooling_guide.md /usr/local/share/ctf_tooling_guide.md

RUN chmod +x /usr/local/bin/agent_runner.py /usr/local/bin/flag_verify_mcp.py /usr/local/bin/flag_submit_mcp.py


FROM sandbox-base AS ci

USER ctf

ENTRYPOINT ["python", "/usr/local/bin/agent_runner.py"]


FROM sandbox-base AS full

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    aeskeyfind \
    binutils \
    binwalk \
    build-essential \
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
    p7zip-full \
    pahole \
    patchelf \
    qemu-system-x86 \
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
    dotnet-sdk-10.0

RUN dotnet tool install ilspycmd

RUN pip install --no-cache-dir \
    https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip \
    idapro \
    libdebug \
    numpy \
    pefile \
    pwntools \
    pycryptodome \
    pyghidra-mcp \
    pyghidra-mcp-cli \
    ropper \
    sympy \
    uv \
    z3-solver && \
    npm install -g @openai/codex

RUN wget --https-only --secure-protocol=TLSv1_2 -qO- 'https://install.pwndbg.re' \
    | sh -s -- -t pwndbg-gdb

# Setup Wine
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    fonts-wine \
    libwine \
    libwine:i386 \
    wine \
    wine32 \
    wine64

# Setup Ghidra installation in sandbox
# Install GPG
RUN apt-get install -y --no-install-recommends gpg

# Setup JDK
RUN wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public \
    | gpg --dearmor \
    | tee /etc/apt/trusted.gpg.d/adoptium.gpg > /dev/null

RUN echo "deb https://packages.adoptium.net/artifactory/deb $(awk -F= '/^VERSION_CODENAME/{print$2}' /etc/os-release) main" \
    | tee /etc/apt/sources.list.d/adoptium.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    temurin-21-jdk

# Download, unzip and copy Ghidra to /opt/ghidra
RUN wget -qO - https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/latest \
    | jq '.assets[0].browser_download_url' | xargs wget -O /tmp/ghidra-latest.zip && \
    unzip /tmp/ghidra-latest.zip -d /tmp/ghidra-latest && \
    mv $(find "/tmp/ghidra-latest" -maxdepth 1 -type d -name "ghidra_*_PUBLIC" | head -n1) /opt/ghidra && \
    rm -rf /tmp/ghidra-latest && rm /tmp/ghidra-latest.zip

ENV GHIDRA_INSTALL_DIR=/opt/ghidra

# Cleanup apt lists
RUN rm -rf /var/lib/apt/lists/*

USER ctf

# Note: apparently needed
RUN dotnet tool restore

ENTRYPOINT ["python", "/usr/local/bin/agent_runner.py"]
