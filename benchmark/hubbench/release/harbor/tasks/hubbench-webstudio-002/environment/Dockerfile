FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17
RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash agent \
    && install -d -o agent -g agent -m 0755 /workspace \
    && install -d -o root -g root -m 0755 /opt/hubbench/hubbench
COPY hubbench/__init__.py /opt/hubbench/hubbench/__init__.py
COPY hubbench/engine /opt/hubbench/hubbench/engine
COPY tools.json /opt/hubbench/tools.json
COPY evidence /workspace/evidence
COPY tool /usr/local/bin/tool
RUN chown -R root:root /opt/hubbench /workspace/evidence \
    && chmod -R u=rwX,go=rX /opt/hubbench /workspace/evidence \
    && chmod 0755 /usr/local/bin/tool
WORKDIR /workspace
ENV HUBBENCH_URL=http://world:8765 HUBBENCH_RUNTIME=/opt/hubbench HUBBENCH_FAMILY=webstudio PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["sh", "-c", "sleep infinity"]
