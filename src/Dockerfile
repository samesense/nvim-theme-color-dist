# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies
# - CairoSVG runtime
# - numpy / scikit-image runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    libjpeg62-turbo \
    libpng16-16 \
    libopenblas0 \
  && rm -rf /var/lib/apt/lists/*

# Python stack required by your scripts
RUN pip install \
    click \
    numpy \
    pandas \
    rich \
    scikit-image \
    cairosvg
