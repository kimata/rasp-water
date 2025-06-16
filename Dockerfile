FROM python:3.12-bookworm AS build

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    build-essential \
    swig

ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/root/.local/bin/:$PATH"

ENV UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN sh /uv-installer.sh && rm /uv-installer.sh

# NOTE: システムにインストール
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=README.md,target=README.md \
    --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --format requirements-txt > requirements.txt \
    && uv pip install -r requirements.txt

# Clean up dependencies
FROM build AS deps-cleanup
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
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
