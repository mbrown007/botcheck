# Backup and Restore Drill (Phase 4)

Last Updated: 2026-02-27

This drill validates RTO/RPO readiness for PostgreSQL state and report artifacts.

## 1. Preconditions

1. Staging stack is running (`postgres`, `api`, `judge`, `minio/localstack`).
2. At least one completed run exists with a report artifact key.
3. You can run Docker commands on the host.

## 2. PostgreSQL Backup

Create logical backup:

```bash
mkdir -p /tmp/botcheck-drill
docker compose exec -T postgres pg_dump -U botcheck -d botcheck > /tmp/botcheck-drill/botcheck.sql
```

Record checksum:

```bash
sha256sum /tmp/botcheck-drill/botcheck.sql > /tmp/botcheck-drill/botcheck.sql.sha256
```

## 3. Artifact Backup (S3/MinIO)

Capture object listing as a point-in-time manifest:

```bash
docker compose exec -T minio mc ls -r local/botcheck-artifacts > /tmp/botcheck-drill/artifacts.ls.txt
```

If using LocalStack/AWS CLI path:

```bash
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
aws --endpoint-url=http://localhost:4566 s3 ls s3://botcheck-artifacts --recursive \
  > /tmp/botcheck-drill/artifacts.ls.txt
```

## 4. Restore Drill (Ephemeral DB)

Start a temporary restore database container:

```bash
docker run --rm -d --name botcheck-restore-db \
  -e POSTGRES_PASSWORD=restore \
  -e POSTGRES_USER=restore \
  -e POSTGRES_DB=restoredb \
  -p 55432:5432 postgres:16
```

Wait for readiness, then restore:

```bash
until docker exec botcheck-restore-db pg_isready -U restore -d restoredb >/dev/null 2>&1; do sleep 1; done
cat /tmp/botcheck-drill/botcheck.sql | docker exec -i botcheck-restore-db psql -U restore -d restoredb
```

Sanity check row counts:

```bash
docker exec -i botcheck-restore-db psql -U restore -d restoredb -c "select count(*) from runs;"
docker exec -i botcheck-restore-db psql -U restore -d restoredb -c "select count(*) from scenarios;"
docker exec -i botcheck-restore-db psql -U restore -d restoredb -c "select count(*) from audit_log;"
docker exec -i botcheck-restore-db psql -U restore -d restoredb -c "select count(*) from schedules;"
```

Tear down:

```bash
docker rm -f botcheck-restore-db
```

## 5. Exit Criteria

1. SQL backup created with checksum.
2. Restore completed without errors.
3. Critical table counts (`runs`, `scenarios`, `audit_log`) are non-zero and plausible.
4. Artifact manifest generated and archived with drill timestamp.
5. Drill report recorded with measured RTO/RPO and follow-up actions.
