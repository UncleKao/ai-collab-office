FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OFFICE_CONFIG=/app/data/office-config.json OFFICE_DATA_DIR=/app/data \
    OFFICE_SECRET_DIR=/app/data/secrets OFFICE_CONTEXT_DIR=/app/data/context
WORKDIR /app
RUN groupadd --gid 10001 office && useradd --uid 10001 --gid office --home-dir /app office && mkdir /app/data && chown office:office /app/data
COPY office*.py owner_proxy.py manage.py office-config.example.json ./
COPY web/ ./web/
USER 10001:10001
EXPOSE 9870
CMD ["sh", "-c", "python3 manage.py init && exec python3 office_server.py --bind 0.0.0.0 --allow-network"]
