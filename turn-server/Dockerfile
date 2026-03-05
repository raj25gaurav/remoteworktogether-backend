FROM debian:bookworm-slim

# Install coturn
RUN apt-get update && \
    apt-get install -y --no-install-recommends coturn && \
    rm -rf /var/lib/apt/lists/*

# Copy config and start script
COPY turnserver.conf /etc/turnserver.conf
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 3478/tcp
EXPOSE 3478/udp
EXPOSE 5349/tcp
EXPOSE 5349/udp
# Relay media port range (keep small for free tier)
EXPOSE 49152-49200/udp

CMD ["/start.sh"]
