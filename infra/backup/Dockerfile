FROM postgres:16-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends restic ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY backup.sh restore-drill.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/restore-drill.sh
