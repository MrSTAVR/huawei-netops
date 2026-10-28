import sqlite3
import json
import os
import sys
from contextlib import contextmanager


def _get_base_path():
    """Возвращает путь к папке, где лежит .exe (или исходный скрипт)."""
    # PyInstaller
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)

    # Nuitka standalone
    if hasattr(sys, '_nuitka_binary_dir'):
        return sys._nuitka_binary_dir

    # Запуск из исходников (.py)
    return os.path.dirname(os.path.abspath(__file__))


DB_FILE = os.path.join(_get_base_path(), "switches.db")


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    # Без этого ON DELETE CASCADE в SQLite не работает
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _conn():
    """Соединение с автоматическим commit/rollback и закрытием."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _rows(sql, params=()):
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _row(sql, params=()):
    with _conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def _insert(sql, params):
    """INSERT, возвращает id новой записи или None при нарушении уникальности."""
    try:
        with _conn() as conn:
            return conn.execute(sql, params).lastrowid
    except sqlite3.IntegrityError:
        return None


def _update(sql, params):
    """UPDATE, возвращает False при нарушении уникальности."""
    try:
        with _conn() as conn:
            conn.execute(sql, params)
        return True
    except sqlite3.IntegrityError:
        return False


def _column_exists(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return column in [row["name"] for row in cur.fetchall()]


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS core_switches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hostname TEXT UNIQUE NOT NULL,
            ip TEXT
        );
        CREATE TABLE IF NOT EXISTS switches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id INTEGER NOT NULL,
            hostname TEXT NOT NULL,
            ip TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('optical', 'copper')),
            uplink_interface TEXT NOT NULL,
            core_switch_id INTEGER NOT NULL,
            core_interface TEXT NOT NULL,
            FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE CASCADE,
            FOREIGN KEY (core_switch_id) REFERENCES core_switches(id)
        );
        CREATE TABLE IF NOT EXISTS switch_interfaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            switch_id INTEGER NOT NULL,
            interface_name TEXT NOT NULL,
            FOREIGN KEY (switch_id) REFERENCES switches(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS vlans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vlan_id INTEGER UNIQUE NOT NULL,
            description TEXT
        );
    """)

    # Миграция для старых баз
    if not _column_exists(conn, "switches", "hostname"):
        conn.execute("ALTER TABLE switches ADD COLUMN hostname TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE switches SET hostname = ip WHERE hostname = ''")

    if not _column_exists(conn, "switches", "core_switch_id"):
        cur.execute("SELECT COUNT(*) as cnt FROM core_switches")
        if cur.fetchone()["cnt"] == 0:
            cur.execute("INSERT INTO core_switches (hostname, ip) VALUES ('default-core', NULL)")
            default_core_id = cur.lastrowid
        else:
            cur.execute("SELECT id FROM core_switches LIMIT 1")
            default_core_id = cur.fetchone()["id"]

        conn.execute(
            f"ALTER TABLE switches ADD COLUMN core_switch_id INTEGER NOT NULL DEFAULT {default_core_id}"
        )

    # Миграция: переименовать cluster_vlans в vlans
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cluster_vlans'")
    if cur.fetchone():
        cur.execute("""
            INSERT OR IGNORE INTO vlans (vlan_id, description)
            SELECT vlan_id, description FROM cluster_vlans
        """)
        cur.execute("DROP TABLE cluster_vlans")

    # Чистка «осиротевших» записей, оставшихся с тех пор, как каскадное удаление не работало
    conn.execute("DELETE FROM switches WHERE cluster_id NOT IN (SELECT id FROM clusters)")
    conn.execute("DELETE FROM switch_interfaces WHERE switch_id NOT IN (SELECT id FROM switches)")

    conn.commit()
    conn.close()


# ---------- Clusters ----------

def add_cluster(name):
    return _insert("INSERT INTO clusters (name) VALUES (?)", (name,))


def update_cluster(cluster_id, name):
    return _update("UPDATE clusters SET name = ? WHERE id = ?", (name, cluster_id))


def list_clusters():
    return _rows("""
        SELECT c.id, c.name, COUNT(s.id) AS switch_count
        FROM clusters c LEFT JOIN switches s ON s.cluster_id = c.id
        GROUP BY c.id ORDER BY c.name
    """)


def get_cluster(cluster_id):
    return _row("SELECT * FROM clusters WHERE id = ?", (cluster_id,))


def delete_cluster(cluster_id):
    with _conn() as conn:
        conn.execute("DELETE FROM clusters WHERE id = ?", (cluster_id,))


# ---------- Core Switches ----------

def add_core_switch(hostname, ip=None):
    return _insert("INSERT INTO core_switches (hostname, ip) VALUES (?, ?)", (hostname, ip))


def update_core_switch(core_id, hostname, ip=None):
    return _update("UPDATE core_switches SET hostname=?, ip=? WHERE id=?", (hostname, ip, core_id))


def list_core_switches():
    return _rows("SELECT id, hostname, ip FROM core_switches ORDER BY hostname")


def get_core_switch(core_id):
    return _row("SELECT * FROM core_switches WHERE id = ?", (core_id,))


def delete_core_switch(core_id):
    """Удаляет Core. Возвращает False, если к нему привязаны TOR."""
    with _conn() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM switches WHERE core_switch_id = ?", (core_id,)).fetchone()[0]
        if cnt:
            return False
        conn.execute("DELETE FROM core_switches WHERE id = ?", (core_id,))
    return True


# ---------- Switches ----------

_SWITCH_SELECT = """
    SELECT s.*, c.name AS cluster_name, cs.hostname AS core_hostname
    FROM switches s
    JOIN clusters c ON s.cluster_id = c.id
    JOIN core_switches cs ON s.core_switch_id = cs.id
"""


def add_switch(cluster_id, hostname, ip, switch_type, uplink, core_switch_id, core_if):
    return _insert(
        """INSERT INTO switches
           (cluster_id, hostname, ip, type, uplink_interface, core_switch_id, core_interface)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (cluster_id, hostname, ip, switch_type, uplink, core_switch_id, core_if)
    )


def update_switch(switch_id, cluster_id, hostname, ip, switch_type, uplink, core_switch_id, core_if):
    return _update(
        """UPDATE switches
           SET cluster_id=?, hostname=?, ip=?, type=?, uplink_interface=?, core_switch_id=?, core_interface=?
           WHERE id=?""",
        (cluster_id, hostname, ip, switch_type, uplink, core_switch_id, core_if, switch_id)
    )


def list_switches(cluster_id=None):
    if cluster_id:
        return _rows(_SWITCH_SELECT + " WHERE s.cluster_id = ? ORDER BY s.type, s.ip", (cluster_id,))
    return _rows(_SWITCH_SELECT + " ORDER BY c.name, s.type, s.ip")


def get_switch(switch_id):
    return _row(_SWITCH_SELECT + " WHERE s.id = ?", (switch_id,))


def delete_switch(switch_id):
    with _conn() as conn:
        conn.execute("DELETE FROM switches WHERE id = ?", (switch_id,))


# ---------- Switch Interfaces ----------

def get_switch_interfaces(switch_id):
    rows = _rows("SELECT interface_name FROM switch_interfaces WHERE switch_id = ? ORDER BY id", (switch_id,))
    return [r["interface_name"] for r in rows]


def set_switch_interfaces(switch_id, interfaces_list):
    with _conn() as conn:
        conn.execute("DELETE FROM switch_interfaces WHERE switch_id = ?", (switch_id,))
        conn.executemany(
            "INSERT INTO switch_interfaces (switch_id, interface_name) VALUES (?, ?)",
            [(switch_id, iface) for iface in interfaces_list]
        )


# ---------- VLANs (глобальная база) ----------

def add_vlan(vlan_id, description=None):
    return _insert("INSERT INTO vlans (vlan_id, description) VALUES (?, ?)", (vlan_id, description))


def update_vlan(vlan_id, description=None):
    return _update("UPDATE vlans SET description = ? WHERE vlan_id = ?", (description, vlan_id))


def list_vlans():
    return _rows("SELECT id, vlan_id, description FROM vlans ORDER BY vlan_id")


def get_vlan_by_id(vlan_id):
    return _row("SELECT * FROM vlans WHERE vlan_id = ?", (vlan_id,))


def delete_vlan(vlan_id):
    with _conn() as conn:
        conn.execute("DELETE FROM vlans WHERE vlan_id = ?", (int(vlan_id),))


# ---------- Export ----------

def export_to_json(filepath):
    data = {
        "vlans": list_vlans(),
        "core_switches": list_core_switches(),
        "clusters": []
    }
    for cl in list_clusters():
        cluster_data = {"name": cl["name"], "switches": []}
        for sw in list_switches(cl["id"]):
            cluster_data["switches"].append({
                "hostname": sw["hostname"],
                "ip": sw["ip"],
                "type": sw["type"],
                "uplink_interface": sw["uplink_interface"],
                "core_switch": sw["core_hostname"],
                "core_interface": sw["core_interface"],
                "interfaces": get_switch_interfaces(sw["id"])
            })
        data["clusters"].append(cluster_data)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data["clusters"])
