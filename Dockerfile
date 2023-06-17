FROM ubuntu:22.04

ARG TARGETPLATFORM

ENV TZ=Asia/Tokyo
ENV DEBIAN_FRONTEND=noninteractive

RUN echo $TARGETPLATFORM

RUN if [ "$TARGETPLATFORM" = "linux/arm64" ]; then GPIO_LIB="python3-rpi.gpio"; fi; \
    apt-get update && apt-get install -y \
    language-pack-ja \
    python3 python3-pip \
    python3-docopt \
    python3-yaml python3-coloredlogs \
    python3-fluent-logger \
    python3-requests \
    python3-schedule \
    python3-flask \
    python3-psutil \
    ${GPIO_LIB} \
 && apt-get clean \
 && rm -rf /va/rlib/apt/lists/*

WORKDIR /opt/rasp-water

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["./flask/app/app.py"]
