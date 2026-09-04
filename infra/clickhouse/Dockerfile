FROM clickhouse/clickhouse-server:24.8
# Cloud Run: serve the HTTP interface on $PORT (8080), single-node, memory-capped for a 2 GiB instance.
COPY config.d/cloudrun.xml /etc/clickhouse-server/config.d/cloudrun.xml
COPY users.d/scripty.xml /etc/clickhouse-server/users.d/scripty.xml
ENV CLICKHOUSE_DO_NOT_CHOWN=1
EXPOSE 8080
