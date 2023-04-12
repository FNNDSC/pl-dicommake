#
# Build with:
#     docker build -t localhost/fnndsc/pl-dicommake .
#
# If you're proxied:
#     export PROXY=<whatever>
#     docker build --build-arg http_proxy=$PROXY -t localhost/fnndsc/pl-dicommake .
#
#
# Python version can be changed, e.g.
# FROM python:3.8
# FROM docker.io/fnndsc/conda:python3.10.2-cuda11.6.0
FROM docker.io/python:3.11.0-slim-bullseye

LABEL org.opencontainers.image.authors="FNNDSC <dev@babyMRI.org>" \
      org.opencontainers.image.title="DICOM image make" \
      org.opencontainers.image.description="A ChRIS plugin that creates a new DICOM file from an existing DICOM and a new image"

WORKDIR /usr/local/src/pl-dicommake

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
ARG extras_require=none
RUN pip install ".[${extras_require}]"

CMD ["dicommake"]
