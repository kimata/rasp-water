FROM ubuntu:22.04

ARG TARGETPLATFORM

ENV TZ=Asia/Tokyo
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    language-pack-ja \
    curl \
    ${GPIO_LIB} \
 && apt-get clean \
 && rm -rf /va/rlib/apt/lists/*

WORKDIR /opt/rasp-water

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml .

RUN poetry install --no-dev

COPY . .

EXPOSE 5000

CMD ["poetry", "run", "./flask/app/app.py"]
