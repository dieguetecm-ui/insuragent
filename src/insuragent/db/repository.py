"""Acceso a la memoria transaccional.

Un único punto de entrada (`Repository`) encapsula todo el SQL. Los agentes
nunca ven un cursor: reciben y devuelven modelos Pydantic, de modo que cambiar
SQLite por PostgreSQL en GCP toca solamente este archivo.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from insuragent.config import get_settings
from insuragent.fs import restringir
from insuragent.schemas.auth import Customer, LoginRequest, Vehicle
from insuragent.schemas.fnol import ClaimReport, EvidenceFile

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Repository:
    """Repositorio sobre SQLite. Seguro de instanciar por hilo/sesión."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_settings().db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # -- infraestructura ----------------------------------------------------

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Conexión con `foreign_keys` activo y commit/rollback automáticos."""
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Crea el esquema si no existe (idempotente) y restringe los permisos."""
        with self.connect() as conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # La base contiene RFC, CURP y siniestros: nunca legible por otros
        # usuarios de la máquina. Se aplica aquí porque `make seed` la recrea.
        restringir(self.db_path)

    def reset(self) -> None:
        """Borra la base y la vuelve a crear. Sólo para el seed y los tests."""
        self.db_path.unlink(missing_ok=True)
        self.initialize()

    # -- clientes -----------------------------------------------------------

    def upsert_customer(self, customer: Customer) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO customers (customer_id, full_name, rfc, curp, phone, email, city,
                                       policy_number, coverage_type, policy_start, policy_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (customer_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    phone     = excluded.phone,
                    email     = excluded.email,
                    city      = excluded.city
                """,
                (
                    customer.customer_id,
                    customer.full_name,
                    customer.rfc,
                    customer.curp,
                    customer.phone,
                    customer.email,
                    customer.city,
                    customer.policy_number,
                    customer.coverage_type,
                    customer.policy_start.isoformat(),
                    customer.policy_end.isoformat(),
                ),
            )
            vehicle = customer.vehicle
            conn.execute(
                """
                INSERT INTO vehicles (vin, customer_id, brand, model, year, plates)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (vin) DO UPDATE SET plates = excluded.plates
                """,
                (
                    vehicle.vin,
                    customer.customer_id,
                    vehicle.brand,
                    vehicle.model,
                    vehicle.year,
                    vehicle.plates,
                ),
            )

    def _row_to_customer(self, row: sqlite3.Row, vehicle_row: sqlite3.Row) -> Customer:
        return Customer(
            customer_id=row["customer_id"],
            full_name=row["full_name"],
            rfc=row["rfc"],
            curp=row["curp"],
            phone=row["phone"],
            email=row["email"],
            city=row["city"],
            policy_number=row["policy_number"],
            coverage_type=row["coverage_type"],
            policy_start=date.fromisoformat(row["policy_start"]),
            policy_end=date.fromisoformat(row["policy_end"]),
            vehicle=Vehicle(
                vin=vehicle_row["vin"],
                brand=vehicle_row["brand"],
                model=vehicle_row["model"],
                year=vehicle_row["year"],
                plates=vehicle_row["plates"],
            ),
        )

    def get_customer(self, customer_id: str) -> Customer | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
            if row is None:
                return None
            vehicle = conn.execute(
                "SELECT * FROM vehicles WHERE customer_id = ?", (customer_id,)
            ).fetchone()
            return self._row_to_customer(row, vehicle) if vehicle else None

    def list_customers(self) -> list[Customer]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()
            vehicles = {
                v["customer_id"]: v for v in conn.execute("SELECT * FROM vehicles").fetchall()
            }
        return [
            self._row_to_customer(row, vehicles[row["customer_id"]])
            for row in rows
            if row["customer_id"] in vehicles
        ]

    def authenticate(self, credentials: LoginRequest) -> Customer | None:
        """Valida las cuatro credenciales del PRD §6.1.

        La búsqueda se hace por número de póliza y la comparación de los tres
        factores restantes ocurre en Python vía `Customer.matches`, para que la
        regla de autenticación viva en un solo lugar auditable.
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE policy_number = ?",
                (credentials.policy_number,),
            ).fetchone()
            if row is None:
                return None
            vehicle = conn.execute(
                "SELECT * FROM vehicles WHERE customer_id = ?", (row["customer_id"],)
            ).fetchone()
        if vehicle is None:
            return None
        customer = self._row_to_customer(row, vehicle)
        return customer if customer.matches(credentials) else None

    # -- siniestros ---------------------------------------------------------

    def save_claim(self, claim: ClaimReport) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO claims (claim_id, customer_id, policy_number, incident_type,
                                    incident_date, location, description,
                                    third_parties_involved, deductible_quoted_mxn, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.claim_id,
                    claim.customer_id,
                    claim.policy_number,
                    claim.incident_type.value,
                    claim.incident_date.isoformat(),
                    claim.location,
                    claim.description,
                    int(claim.third_parties_involved),
                    claim.deductible_quoted_mxn,
                    claim.created_at.isoformat(),
                ),
            )
            for item in claim.evidence:
                conn.execute(
                    """
                    INSERT INTO evidence (claim_id, filename, stored_path, content_type,
                                          size_bytes, uploaded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim.claim_id,
                        item.filename,
                        str(item.stored_path),
                        item.content_type,
                        item.size_bytes,
                        item.uploaded_at.isoformat(),
                    ),
                )

    def next_claim_id(self) -> str:
        with self.connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"]
        return f"SIN-{datetime.now():%Y%m}-{count + 1:05d}"

    def list_claims(self, customer_id: str) -> list[dict]:
        """Historial de siniestros — memoria de largo plazo (PRD §3.2)."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM claims WHERE customer_id = ? ORDER BY created_at DESC",
                (customer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_evidence(self, claim_id: str) -> list[EvidenceFile]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE claim_id = ? ORDER BY evidence_id", (claim_id,)
            ).fetchall()
        return [
            EvidenceFile(
                filename=row["filename"],
                stored_path=Path(row["stored_path"]),
                content_type=row["content_type"],
                size_bytes=row["size_bytes"],
                uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
            )
            for row in rows
        ]

    # -- memoria conversacional --------------------------------------------

    def append_turn(
        self, customer_id: str, run_id: str, role: str, content: str, route: str | None = None
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_turns (customer_id, run_id, role, content, route, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (customer_id, run_id, role, content, route, datetime.now().isoformat()),
            )

    def recent_turns(self, customer_id: str, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, route, created_at FROM conversation_turns
                WHERE customer_id = ? ORDER BY turn_id DESC LIMIT ?
                """,
                (customer_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]
