# valheim-status-page: a status page for mbround18/valheim servers.
# One container: nginx serves the page, a small Python worker keeps its data up to date.
FROM nginx:1.27-alpine

RUN apk add --no-cache python3 tzdata

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/entrypoint.sh /entrypoint.sh
COPY web/ /usr/share/nginx/html/
COPY worker/ /app/worker/

RUN chmod +x /entrypoint.sh \
 && mkdir -p /usr/share/nginx/html/data /data /config

ENV VSP_CONFIG=/config/config.toml \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
