# Container image that runs your code
FROM alpine:latest

RUN apk update && \
    apk add python3 && \
    rm -rf /var/cache/apk/*
# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.py /entrypoint.py

WORKDIR /data

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/entrypoint.py"]
