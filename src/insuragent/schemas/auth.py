"""Contratos de autenticación simulada (PRD §6.1).

Los identificadores mexicanos (RFC, CURP) son datos personales regulados por la
LFPDPPP. Para que la PoC pueda compartirse como demo sin ambigüedad, todos los
identificadores sintéticos llevan un marcador explícito:

* RFC  → siempre inicia con ``XXX`` (prefijo reservado, no asignable a personas)
* CURP → siempre inicia con ``XXXX`` y usa el código de entidad ``NE``

`is_synthetic()` verifica ese marcador y es lo que impide que la PoC ingiera
por accidente un identificador real.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

RFC_PATTERN = re.compile(r"^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$")
CURP_PATTERN = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z]{2}[A-Z]{3}[A-Z0-9]\d$")
POLICY_PATTERN = re.compile(r"^AUT-\d{4}-\d{6}$")

SYNTHETIC_RFC_PREFIX = "XXX"
SYNTHETIC_CURP_PREFIX = "XXXX"


class LoginRequest(BaseModel):
    """Credenciales que teclea el asegurado en la pantalla de acceso."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    policy_number: str = Field(description="Número de póliza, formato AUT-AAAA-NNNNNN")
    rfc: str = Field(description="RFC sintético de 13 posiciones")
    curp: str = Field(description="CURP sintética de 18 posiciones")
    phone_last3: str = Field(description="Últimos 3 dígitos del celular registrado")

    @field_validator("policy_number", "rfc", "curp", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("policy_number")
    @classmethod
    def _check_policy(cls, value: str) -> str:
        if not POLICY_PATTERN.match(value):
            raise ValueError("El número de póliza debe tener el formato AUT-AAAA-NNNNNN")
        return value

    @field_validator("rfc")
    @classmethod
    def _check_rfc(cls, value: str) -> str:
        if not RFC_PATTERN.match(value):
            raise ValueError(
                "RFC inválido: se esperan 13 posiciones (4 letras, 6 dígitos, 3 alfanuméricos)"
            )
        return value

    @field_validator("curp")
    @classmethod
    def _check_curp(cls, value: str) -> str:
        if not CURP_PATTERN.match(value):
            raise ValueError("CURP inválida: se esperan 18 posiciones con el formato oficial")
        return value

    @field_validator("phone_last3")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        if not (len(value) == 3 and value.isdigit()):
            raise ValueError("Se esperan exactamente 3 dígitos del celular")
        return value

    def is_synthetic(self) -> bool:
        """True si ambos identificadores llevan el marcador de dato sintético."""
        return self.rfc.startswith(SYNTHETIC_RFC_PREFIX) and self.curp.startswith(
            SYNTHETIC_CURP_PREFIX
        )


class Vehicle(BaseModel):
    """Vehículo asegurado bajo una póliza."""

    model_config = ConfigDict(str_strip_whitespace=True)

    vin: str = Field(min_length=17, max_length=17)
    brand: str
    model: str
    year: int = Field(ge=1990, le=2030)
    plates: str = Field(min_length=6, max_length=8)


class Customer(BaseModel):
    """Asegurado sintético tal como vive en la base transaccional."""

    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    full_name: str
    rfc: str
    curp: str
    phone: str = Field(min_length=10, max_length=10)
    email: str
    city: str
    policy_number: str
    coverage_type: str = Field(description="basica | amplia | rc")
    policy_start: date
    policy_end: date
    vehicle: Vehicle

    @property
    def phone_last3(self) -> str:
        return self.phone[-3:]

    def matches(self, credentials: LoginRequest) -> bool:
        """Compara las cuatro credenciales exigidas por el PRD §6.1."""
        return (
            self.policy_number == credentials.policy_number
            and self.rfc == credentials.rfc
            and self.curp == credentials.curp
            and self.phone_last3 == credentials.phone_last3
        )
