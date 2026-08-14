ARG BUILD_FROM=python:3.11-alpine
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    git \
    openssh-client \
    bash \
    ca-certificates

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app
COPY run.sh /app/run.sh

RUN chmod +x /app/run.sh

ENTRYPOINT ["/app/run.sh"]
