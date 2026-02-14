FROM python:3.11-slim

RUN useradd -m -u 1000 ctf

WORKDIR /workspace

COPY agent_runner.py /usr/local/bin/agent_runner.py
COPY agent_prompt.txt /usr/local/share/agent_prompt.txt

RUN chmod +x /usr/local/bin/agent_runner.py

USER ctf

ENTRYPOINT ["python", "/usr/local/bin/agent_runner.py"]
