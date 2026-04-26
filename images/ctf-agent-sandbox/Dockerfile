FROM condaforge/miniforge3:26.1.0-0 AS sandbox-base

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    bash \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

FROM sandbox-base AS ci

# NOTE: Done here to avoid messing with `conda activate` for full image too much
RUN groupmod -g 1001 ubuntu && usermod -u 1001 -g 1001 ubuntu && \
    useradd -m -u 1000 -s /bin/bash ctf && \
    mkdir -p /workspace/chal /workspace/run /home/ctf/.codex && \
    chown -R ctf:ctf /workspace /home/ctf

# NOTE: Done here to avoid costly rebuild of full image every time we need to change sth in tooling guide/prompt
COPY agent_runner.py /usr/local/bin/agent_runner.py
COPY flag_verify_mcp.py /usr/local/bin/flag_verifthy_mcp.py
COPY flag_submit_mcp.py /usr/local/bin/flag_submit_mcp.py
COPY agent_prompt.txt /usr/local/share/agent_prompt.txt
COPY ctf_tooling_guide.md /usr/local/share/ctf_tooling_guide.md

RUN chmod +x /usr/local/bin/agent_runner.py /usr/local/bin/flag_verify_mcp.py /usr/local/bin/flag_submit_mcp.py

USER ctf
WORKDIR /workspace
ENTRYPOINT ["python3", "/usr/local/bin/agent_runner.py"]

FROM sandbox-base AS full

# Install SageMath and create CTF Python profile based on it
RUN mamba create -y -n ctf sage python=3.13 && \
    echo "conda activate ctf" >> ~/.bashrc && \
    echo "conda activate ctf" >> /etc/skel/.bashrc

RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    aeskeyfind \
    binutils \
    binwalk \
    build-essential \
    cpio \
    curl \
    dotnet-sdk-8.0 \
    dotnet-sdk-10.0 \
    fasm \
    file \
    fonts-wine \
    gdb \
    gdb-multiarch \
    git \
    golang \
    jq \
    ltrace \
    libwine \
    libwine:i386 \
    ncat \
    netcat-openbsd \
    nodejs \
    npm \
    nvidia-cuda-toolkit \
    openjdk-21-jdk \
    p7zip-full \
    pahole \
    patchelf \
    qemu-system-x86 \
    ripgrep \
    socat \
    ssh \
    strace \
    tshark \
    unzip \
    vim \
    vim-common \
    wget \
    wine \
    wine32 \
    wine64 \
    xxd \
    zip

RUN npm install -g @openai/codex

ENV GOBIN=/usr/local/bin
RUN go install github.com/ffuf/ffuf/v2@latest && \
    go install github.com/OJ/gobuster/v3@latest

# Download, untar and copy Zig toolchain to /opt/zig, then add to PATH
RUN curl -fSSL https://ziglang.org/download/index.json | jq -r 'to_entries | map(select(.value["x86_64-linux"]?)) | max_by(.value.date) | .value["x86_64-linux"].tarball' | \
    xargs wget -O /tmp/zig-latest.tar.xz && \
    mkdir -p /opt/zig && tar -C /opt/zig -xf /tmp/zig-latest.tar.xz --strip-components=1 && \
    rm /tmp/zig-latest.tar.xz

ENV PATH="/opt/zig:$PATH"

# Download, unzip and copy Ghidra to /opt/ghidra
RUN wget -qO - https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/latest \
    | jq '.assets[0].browser_download_url' | xargs wget -O /tmp/ghidra-latest.zip && \
    unzip /tmp/ghidra-latest.zip -d /tmp/ghidra-latest && \
    mv $(find "/tmp/ghidra-latest" -maxdepth 1 -type d -name "ghidra_*_PUBLIC" | head -n1) /opt/ghidra && \
    rm -rf /tmp/ghidra-latest && rm /tmp/ghidra-latest.zip

ENV GHIDRA_INSTALL_DIR=/opt/ghidra

RUN dotnet tool install ilspycmd

# Hacky hack for Pip packages to install in our conda env
SHELL ["conda", "run", "-n", "ctf", "/bin/bash", "-c"]
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
    scapy \
    sympy \
    uv \
    z3-solver

# Setup pwndbg
RUN curl --proto '=https' --tlsv1.2 -LsSf 'https://install.pwndbg.re' | sh -s -- -t pwndbg-gdb && \
    ln -s /usr/local/bin/pwndbg /usr/local/bin/gdb

# NOTE: Same reasoning as wíth CI
COPY agent_runner.py /usr/local/bin/agent_runner.py
COPY flag_verify_mcp.py /usr/local/bin/flag_verify_mcp.py
COPY flag_submit_mcp.py /usr/local/bin/flag_submit_mcp.py
COPY agent_prompt.txt /usr/local/share/agent_prompt.txt
COPY ctf_tooling_guide.md /usr/local/share/ctf_tooling_guide.md

# NOTE: Done here to avoid messing with `conda activate` too much, same reason as with CI...
RUN groupmod -g 1001 ubuntu && usermod -u 1001 -g 1001 ubuntu && \
    useradd -m -u 1000 -s /bin/bash ctf && \
    mkdir -p /workspace/chal /workspace/run /home/ctf/.codex && \
    chown -R ctf:ctf /workspace /home/ctf

RUN chmod +x /usr/local/bin/agent_runner.py /usr/local/bin/flag_verify_mcp.py /usr/local/bin/flag_submit_mcp.py

USER ctf



# Hacky hack of hacks for `pip install` in user to not spam warnings 24/7
ENV PATH="/home/ctf/.local/bin:$PATH"

# Necessary for ilspycmd to run
RUN dotnet tool restore

WORKDIR /workspace
# Evil hack - but I'm not sure if it works without this? Also this craps into stdout because of `conda run` not having disablable logger
ENTRYPOINT ["conda", "run", "-n", "ctf", "--no-capture-output", "python3", "/usr/local/bin/agent_runner.py"]