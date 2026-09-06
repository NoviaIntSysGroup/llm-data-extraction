# syntax=docker/dockerfile:1

FROM python:3.11-slim

# 1. Install uv directly from the official Astral image (fastest way to install it)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
# UV_COMPILE_BYTECODE: Compiles Python to .pyc files for faster startup
# UV_LINK_MODE=copy: Best practice for Docker to prevent hardlink issues
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# System dependencies (cached via BuildKit)
RUN rm -f /etc/apt/apt.conf.d/docker-clean; echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential

# Copy only dependency files first
COPY pyproject.toml setup.py* setup.cfg* README.md* ./

# Trick setuptools by creating an empty src directory
RUN mkdir src

# 2. INSTALL DEPENDENCIES WITH UV
# We mount uv's cache directory instead of pip's.
# --system tells uv to install into the global Python environment (replacing standard pip behavior)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e .

# Copy the rest of the code
COPY . .

EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", "src/chatbot/feed_app.py", "--server.port=8501", "--server.address=0.0.0.0"]