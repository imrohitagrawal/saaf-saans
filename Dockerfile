# SaafSaans -- server-rendered FastAPI, no build step, no JavaScript toolchain.
#
# Targets Hugging Face Spaces (Docker SDK), which runs containers as UID 1000
# and routes to the port declared as `app_port` in the Space's README front
# matter. PORT is read from the environment so the same image also runs on
# Fly.io, Cloud Run or a plain `docker run -p`, none of which use 7860.
FROM python:3.11-slim

# Fail fast and log immediately: a buffered stdout hides startup errors behind
# the platform's "container failed to start" with nothing to read.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# UID 1000 is not a preference here -- Hugging Face Spaces requires it.
RUN useradd --create-home --uid 1000 app
USER app
WORKDIR /home/app

# Requirements first so a code change does not re-resolve the dependency tree.
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
ENV PATH="/home/app/.local/bin:${PATH}"

COPY --chown=app:app saafsaans ./saafsaans

EXPOSE 7860

# The container is healthy when the app can answer for itself. /health reports
# which back ends are actually wired up (es / waqi / llm), so a green check
# means "serving", not merely "process alive".
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','7860')+'/health', timeout=4).status == 200 else 1)"

# --forwarded-allow-ips is not decoration. Every host in docs/DEPLOY.md
# terminates TLS at an edge proxy, and uvicorn ignores X-Forwarded-Proto from
# anything but 127.0.0.1 by default -- so without this the app believes it is
# serving plain http and stops marking the session cookie Secure. The container
# is only reachable through that proxy, so trusting it is the correct scope.
CMD ["sh", "-c", "exec uvicorn saafsaans.web.main:app --host 0.0.0.0 --port ${PORT} --forwarded-allow-ips='*'"]
