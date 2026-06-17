FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/sjbrownrigg/discogstagger3"
LABEL org.opencontainers.image.description="Audio file metadata tagger using the Discogs API"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        shntool \
        flac \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e .

# Expected volume mount points
VOLUME ["/music", "/config", "/cache"]

ENTRYPOINT ["discogstagger"]
CMD ["-c", "/config/config.yaml", "-w"]
