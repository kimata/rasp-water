FROM python:3.12-bookworm AS build

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    curl \
    clang

ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH=/root/.rye/shims/:$PATH

RUN --mount=type=cache,target=/tmp/rye-cache \
    if [ ! -f /tmp/rye-cache/rye-install.sh ]; then \
        curl -sSfL https://rye.astral.sh/get -o /tmp/rye-cache/rye-install.sh; \
    fi && \
    RYE_NO_AUTO_INSTALL=1 RYE_INSTALL_OPTION="--yes" bash /tmp/rye-cache/rye-install.sh

COPY pyproject.toml .python-version README.md .

RUN rye lock

# First install core dependencies that rarely change
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    grep -E "^(flask|requests|pydantic|influxdb-client|coloredlogs|psutil)" requirements.lock | grep -v "#" > requirements-core.txt && \
    pip install --break-system-packages -r requirements-core.txt

# Then install all dependencies (pip will skip already installed ones)
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --break-system-packages -r requirements.lock


# Clean up dependencies
FROM build AS deps-cleanup
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --break-system-packages pip-autoremove && \
    pip-autoremove setuptools wheel pip -y && \
    find /usr/local/lib/python3.12/site-packages -name "*.pyc" -delete && \
    find /usr/local/lib/python3.12/site-packages -name "__pycache__" -type d -delete


FROM python:3.12-slim-bookworm AS prod

ARG IMAGE_BUILD_DATE
ENV IMAGE_BUILD_DATE=${IMAGE_BUILD_DATE}

ENV TZ=Asia/Tokyo

COPY --from=deps-cleanup /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

WORKDIR /opt/rasp-water

COPY . .

EXPOSE 5000

CMD ["./flask/src/app.py"]
