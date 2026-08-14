ARG BUILD_FROM=python:3.11-alpine
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    python3 \
    py3-pip \
    git \
    openssh-client \
    bash \
    ca-certificates

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY run.sh /app/run.sh

RUN chmod +x /app/run.sh

ENTRYPOINT ["/app/run.sh"]
