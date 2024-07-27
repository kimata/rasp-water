FROM python:3.11.4-bookworm AS build

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    gcc \
    curl \
    python3 \
    python3-dev

WORKDIR /opt/rasp-water

ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/root/.local/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python3 - \
    && poetry config virtualenvs.create false

RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=cache,target=/root/.cache/pypoetry,sharing=locked \
    poetry install --no-interaction

FROM python:3.11.4-slim-bookworm AS prod

ARG IMAGE_BUILD_DATE

ENV TZ=Asia/Tokyo
ENV IMAGE_BUILD_DATE=${IMAGE_BUILD_DATE}

COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

WORKDIR /opt/rasp-water

COPY . .

EXPOSE 5000

CMD ["./flask/app/app.py"]
