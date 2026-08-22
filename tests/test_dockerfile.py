from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"
DOCKERIGNORE = Path(__file__).resolve().parents[1] / ".dockerignore"


def test_dockerfile_sets_default_bind_port_for_runtime_and_healthcheck():
    dockerfile = DOCKERFILE.read_text()

    assert "ENV HOST=0.0.0.0" in dockerfile
    assert "ENV PORT=5690" in dockerfile
    assert "http://localhost:${PORT:-5690}/health" in dockerfile


def test_dockerignore_excludes_local_dev_database_artifacts():
    """Dockerfile does `COPY . /app`; the dev SQLite DB and secrets.json
    live under database/ (see app/config.py), so they must never be
    baked into the image."""
    dockerignore_lines = {
        line.strip()
        for line in DOCKERIGNORE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert "database/" in dockerignore_lines
    assert "data/" in dockerignore_lines
    assert "*.db" in dockerignore_lines
    assert "*.db-wal" in dockerignore_lines
    assert "*.db-shm" in dockerignore_lines
