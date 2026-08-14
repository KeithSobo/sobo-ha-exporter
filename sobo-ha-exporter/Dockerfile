FROM python:3.11-alpine

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    git \
    openssh-client \
    bash \
    ca-certificates \
    tzdata

RUN cat /etc/os-release \
    && command -v python \
    && command -v pip \
    && /usr/local/bin/python --version \
    && /usr/local/bin/python -m pip --version

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN /usr/local/bin/python -m pip install \
    --no-cache-dir \
    -r /app/requirements.txt

COPY app /app/app
COPY run.sh /app/run.sh

RUN chmod +x /app/run.sh

ENTRYPOINT ["/app/run.sh"]
