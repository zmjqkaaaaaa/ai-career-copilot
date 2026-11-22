FROM python:3.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 career \
    && useradd --uid 10001 --gid career --no-create-home --shell /usr/sbin/nologin career \
    && install -d -o career -g career -m 0700 /data/resumes

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
