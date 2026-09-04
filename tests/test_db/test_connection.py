import sqlite3
import pytest
from ace.db.connection import create_project, open_project, checkpoint_and_close
from ace.db.migrations import NewerSchemaVersionError
from ace.db.schema import ACE_APPLICATION_ID, SCHEMA_VERSION


def test_create_project_creates_file(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    conn.close()
    assert tmp_db.exists()


def test_create_project_inserts_manager_role(tmp_db):
    conn = create_project(tmp_db, "Test Project", description="A test")
    row = conn.execute("SELECT name, file_role FROM project").fetchone()
    assert row["name"] == "Test Project"
    assert row["file_role"] == "manager"
    conn.close()


def test_create_project_cleans_partial_files_when_schema_creation_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "partial.ace"

    def fail_schema(_conn):
        raise sqlite3.OperationalError("simulated disk failure")

    monkeypatch.setattr("ace.db.connection.create_schema", fail_schema)

    with pytest.raises(sqlite3.OperationalError):
        create_project(path, "Partial")

    assert not path.exists()
    assert not path.with_name(f"{path.name}-wal").exists()
    assert not path.with_name(f"{path.name}-shm").exists()


def test_open_project_validates_application_id(tmp_path):
    # Create a plain SQLite file (no ACE schema)
    plain_db = tmp_path / "plain.ace"
    plain_conn = sqlite3.connect(str(plain_db))
    plain_conn.execute("CREATE TABLE dummy (id INTEGER)")
    plain_conn.commit()
    plain_conn.close()

    with pytest.raises(ValueError):
        open_project(plain_db)


def test_open_project_rejects_newer_schema_and_closes_connection(
    tmp_path, monkeypatch
):
    path = tmp_path / "future.ace"
    conn = create_project(path, "Future")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    real_connect = sqlite3.connect
    opened = []

    class TrackingConnection(sqlite3.Connection):
        was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        tracked = real_connect(*args, **kwargs)
        opened.append(tracked)
        return tracked

    monkeypatch.setattr("ace.db.connection.sqlite3.connect", tracked_connect)

    with pytest.raises(NewerSchemaVersionError) as error:
        open_project(path)

    assert error.value.file_version == SCHEMA_VERSION + 1
    assert error.value.supported_version == SCHEMA_VERSION
    assert len(opened) == 1
    assert opened[0].was_closed


def test_open_project_enables_foreign_keys(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    conn.close()

    conn = open_project(tmp_db)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1
    conn.close()


def test_open_project_uses_wal_mode(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    conn.close()

    conn = open_project(tmp_db)
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"
    conn.close()


def test_create_project_creates_default_coder(tmp_path):
    from ace.db.connection import create_project, checkpoint_and_close
    path = tmp_path / "test.ace"
    conn = create_project(path, "Test")
    row = conn.execute("SELECT * FROM coder").fetchone()
    assert row is not None
    assert row["name"] == "default"
    checkpoint_and_close(conn)


def test_checkpoint_and_close_switches_to_delete_mode(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    checkpoint_and_close(conn)

    assert not tmp_db.with_name(f"{tmp_db.name}-wal").exists()
    assert not tmp_db.with_name(f"{tmp_db.name}-shm").exists()

    # Re-open to check journal mode was switched back
    verify_conn = sqlite3.connect(str(tmp_db))
    row = verify_conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "delete"
    verify_conn.close()
