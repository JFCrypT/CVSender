#!/usr/bin/env python3
"""Envía CV por correo usando plantillas guardadas en Thunderbird.

Flujo:
  1. Preparar o actualizar las plantillas (Thunderbird puede permanecer abierto):
       python3 cvsender.py --preparar
  2. Probar sin enviar:
       python3 cvsender.py resultados.csv --dry-run
  3. Enviar todas las filas válidas:
       python3 cvsender.py resultados.csv

No requiere paquetes externos. Compatible con Python 3.11+.
"""

from __future__ import annotations

import argparse
import configparser
import csv
import getpass
import hashlib
import json
import mailbox
import os
import re
import shutil
import smtplib
import ssl
import sys
import time
import unicodedata
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import formatdate, make_msgid, parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

APP_NAME = "CVSender"
PROJECT_DIR = Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / "CVSender_state"
TEMPLATES_DIR = STATE_DIR / "plantillas"
SMTP_STATE_FILE = STATE_DIR / "smtp.json"
DEFAULT_ARCHIVE_DIR = STATE_DIR / "archivo_eml"
DEFAULT_LOG_FILE = STATE_DIR / "envios.csv"

CSV_HEADERS = [
    "organizacion_o_reparticion",
    "puesto_o_area_recomendada",
    "idioma_recomendado",
    "correo",
    "recomendacion",
]

TEMPLATE_SUBJECTS = {
    "ingles": "CV Submission",
    "español-industrial": "Enviar CV",
    "español-académico": "Enviar CV: docencia",
}

TEMPLATE_CACHE_NAMES = {
    "ingles": "ingles.eml",
    "español-industrial": "espanol-industrial.eml",
    "español-académico": "espanol-academico.eml",
}

DROP_HEADERS = {
    "to",
    "cc",
    "bcc",
    "date",
    "message-id",
    "return-path",
    "delivered-to",
    "received",
    "status",
    "x-status",
    "x-uidl",
    "x-unsent",
    "content-length",
    "lines",
}

EMAIL_RE = re.compile(r"^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$")
PREF_RE = re.compile(r'^user_pref\("(?P<key>(?:[^"\\]|\\.)*)",\s*(?P<value>.+)\);$')


class AppError(RuntimeError):
    """Error de uso o validación que debe mostrarse sin traceback."""


@dataclass(frozen=True)
class CsvEntry:
    line_number: int
    organizacion_o_reparticion: str
    puesto_o_area_recomendada: str
    idioma_recomendado: str
    correo: str
    recomendacion: str


@dataclass(frozen=True)
class SmtpSettings:
    sender_email: str
    host: str
    port: int
    security: str  # plain | starttls | ssl
    username: str
    auth_method: int
    smtp_key: str
    profile_path: str


@dataclass(frozen=True)
class TemplateCandidate:
    subject: str
    message: EmailMessage
    source: str
    position: int
    timestamp: float
    order: int


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cvsender.py",
        description=(
            "Envía todas las direcciones de un CSV usando las tres plantillas "
            "de Thunderbird definidas por idioma_recomendado."
        )
    )
    parser.add_argument("csv", nargs="?", type=Path, help="CSV UTF-8 generado por Asistente")
    parser.add_argument(
        "--preparar",
        action="store_true",
        help=(
            "Extrae/actualiza las plantillas y la configuración SMTP desde Thunderbird "
            "mediante una copia de solo lectura; Thunderbird puede permanecer abierto"
        ),
    )
    parser.add_argument(
        "--profile",
        type=Path,
        help="Ruta explícita al perfil de Thunderbird (opcional)",
    )
    parser.add_argument(
        "--templates-path",
        type=Path,
        help="Ruta explícita al mbox/Maildir de Templates (opcional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Genera y archiva los .eml, pero no conecta al servidor SMTP",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=15.0,
        help="Segundos de pausa entre envíos (predeterminado: 15)",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help=f"Directorio de archivo .eml (predeterminado: {DEFAULT_ARCHIVE_DIR})",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG_FILE,
        help=f"CSV de registro de envíos (predeterminado: {DEFAULT_LOG_FILE})",
    )
    parser.add_argument(
        "--smtp-password-env",
        default="CVSENDER_SMTP_PASSWORD",
        help="Variable de entorno que contiene la contraseña SMTP",
    )
    parser.add_argument("--smtp-host", help="Sobrescribe el servidor SMTP detectado")
    parser.add_argument("--smtp-port", type=int, help="Sobrescribe el puerto SMTP detectado")
    parser.add_argument(
        "--smtp-security",
        choices=("plain", "starttls", "ssl"),
        help="Sobrescribe la seguridad SMTP detectada",
    )
    parser.add_argument("--smtp-user", help="Sobrescribe el usuario SMTP detectado")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout SMTP en segundos (predeterminado: 30)",
    )
    parser.add_argument(
        "--permitir-duplicados",
        action="store_true",
        help="Permite repetir la misma dirección en varias filas del mismo CSV",
    )
    parser.add_argument(
        "--debug-smtp",
        action="store_true",
        help="Muestra la conversación SMTP (puede exponer metadatos; no muestra la contraseña)",
    )
    args = parser.parse_args(argv)

    if not args.preparar and args.csv is None:
        parser.error("debe indicar un CSV o usar --preparar")
    if args.preparar and args.csv is not None:
        parser.error("--preparar no debe combinarse con un CSV")
    if args.delay < 0:
        parser.error("--delay no puede ser negativo")
    return args


def thunderbird_is_running() -> bool:
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            comm = (item / "comm").read_text(encoding="utf-8", errors="ignore").strip().lower()
            executable = (item / "exe").resolve().name.lower()
        except (OSError, PermissionError):
            continue
        if "thunderbird" in comm or "thunderbird" in executable:
            return True
    return False


def profiles_ini_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / ".thunderbird" / "profiles.ini",
        home / "snap" / "thunderbird" / "common" / ".thunderbird" / "profiles.ini",
        home / ".var" / "app" / "org.mozilla.Thunderbird" / ".thunderbird" / "profiles.ini",
        home / ".mozilla-thunderbird" / "profiles.ini",
    ]


def resolve_profile_path(base: Path, path_value: str, is_relative: bool) -> Path:
    path = Path(path_value)
    return (base / path).resolve() if is_relative else path.expanduser().resolve()


def discover_thunderbird_profile(explicit: Path | None = None) -> Path:
    if explicit:
        profile = explicit.expanduser().resolve()
        if not (profile / "prefs.js").is_file():
            raise AppError(f"El perfil indicado no contiene prefs.js: {profile}")
        return profile

    found: list[tuple[int, float, Path]] = []
    for ini_path in profiles_ini_candidates():
        if not ini_path.is_file():
            continue
        parser = configparser.RawConfigParser()
        try:
            parser.read(ini_path, encoding="utf-8")
        except (configparser.Error, OSError):
            continue
        base = ini_path.parent
        install_defaults: set[str] = set()
        for section in parser.sections():
            if section.lower().startswith("install") and parser.has_option(section, "Default"):
                install_defaults.add(parser.get(section, "Default"))

        for section in parser.sections():
            if not section.lower().startswith("profile") or not parser.has_option(section, "Path"):
                continue
            path_value = parser.get(section, "Path")
            is_relative = parser.getboolean(section, "IsRelative", fallback=True)
            profile = resolve_profile_path(base, path_value, is_relative)
            prefs = profile / "prefs.js"
            if not prefs.is_file():
                continue
            score = 0
            if parser.getboolean(section, "Default", fallback=False):
                score += 10
            if path_value in install_defaults:
                score += 20
            try:
                mtime = prefs.stat().st_mtime
            except OSError:
                mtime = 0.0
            found.append((score, mtime, profile))

    if not found:
        raise AppError(
            "No se encontró un perfil de Thunderbird. Use --profile /ruta/al/perfil."
        )
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return found[0][2]


def read_stable_bytes(path: Path, attempts: int = 5, pause: float = 0.2) -> bytes:
    """Lee un archivo que puede estar siendo actualizado y exige una instantánea estable."""
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            before = path.stat()
            content = path.read_bytes()
            after = path.stat()
        except (OSError, FileNotFoundError) as exc:
            last_error = exc
            time.sleep(pause)
            continue
        if (
            before.st_size == after.st_size == len(content)
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return content
        time.sleep(pause)
    detail = f": {last_error}" if last_error else ""
    raise AppError(
        f"No se pudo obtener una instantánea estable de {path} después de {attempts} intentos{detail}"
    )


def parse_prefs_js(profile: Path) -> dict[str, Any]:
    prefs_file = profile / "prefs.js"
    prefs: dict[str, Any] = {}
    try:
        lines = read_stable_bytes(prefs_file).decode(
            "utf-8", errors="replace"
        ).splitlines()
    except OSError as exc:
        raise AppError(f"No se pudo leer {prefs_file}: {exc}") from exc

    for raw_line in lines:
        match = PREF_RE.match(raw_line.strip())
        if not match:
            continue
        key_literal = '"' + match.group("key") + '"'
        try:
            key = json.loads(key_literal)
            value = json.loads(match.group("value"))
        except json.JSONDecodeError:
            continue
        prefs[key] = value
    return prefs


def stable_copy_file(source: Path, destination: Path, attempts: int = 5, pause: float = 0.2) -> None:
    """Copia un archivo solo cuando no cambia durante la operación."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            before = source.stat()
            shutil.copy2(source, destination)
            after = source.stat()
            copied = destination.stat()
        except (OSError, FileNotFoundError) as exc:
            last_error = exc
            time.sleep(pause)
            continue
        if (
            before.st_size == after.st_size == copied.st_size
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return
        time.sleep(pause)
    detail = f": {last_error}" if last_error else ""
    raise AppError(
        f"No se pudo copiar de forma estable {source} después de {attempts} intentos{detail}"
    )


def maildir_signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    signature: list[tuple[str, int, int]] = []
    for folder_name in ("cur", "new"):
        folder = root / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir(), key=lambda item: item.name):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            signature.append((str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


def stable_copy_maildir(source: Path, destination: Path, attempts: int = 5, pause: float = 0.2) -> None:
    """Crea una instantánea estable de un Maildir sin bloquear Thunderbird."""
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            before = maildir_signature(source)
            if destination.exists():
                shutil.rmtree(destination)
            destination.mkdir(parents=True, exist_ok=True)
            for folder_name in ("cur", "new", "tmp"):
                src_folder = source / folder_name
                dst_folder = destination / folder_name
                if src_folder.is_dir():
                    shutil.copytree(src_folder, dst_folder)
                else:
                    dst_folder.mkdir(parents=True, exist_ok=True)
            after = maildir_signature(source)
        except (OSError, FileNotFoundError) as exc:
            last_error = exc
            time.sleep(pause)
            continue
        if before == after:
            return
        time.sleep(pause)
    detail = f": {last_error}" if last_error else ""
    raise AppError(
        f"No se pudo copiar de forma estable el Maildir {source} después de {attempts} intentos{detail}"
    )


def snapshot_template_stores(
    stores: Iterable[tuple[str, Path]], snapshot_root: Path
) -> list[tuple[str, Path]]:
    """Copia los almacenes de plantillas a una instantánea local de solo lectura."""
    snapshots: list[tuple[str, Path]] = []
    for index, (kind, source) in enumerate(stores, start=1):
        if kind == "mbox":
            destination = snapshot_root / f"templates-{index}.mbox"
            stable_copy_file(source, destination)
        elif kind == "maildir":
            destination = snapshot_root / f"templates-{index}.maildir"
            stable_copy_maildir(source, destination)
        else:
            raise AppError(f"Tipo de almacén no soportado: {kind}")
        snapshots.append((kind, destination))
    return snapshots


def discover_template_stores(profile: Path, explicit: Path | None = None) -> list[tuple[str, Path]]:
    if explicit:
        path = explicit.expanduser().resolve()
        if path.is_file():
            return [("mbox", path)]
        if path.is_dir() and (path / "cur").is_dir():
            return [("maildir", path)]
        raise AppError(f"La ruta de Templates no es un mbox ni un Maildir válido: {path}")

    stores: list[tuple[str, Path]] = []
    accepted_names = {"templates", "plantillas"}
    for root_name in ("Mail", "ImapMail"):
        root = profile / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.name.casefold() not in accepted_names:
                continue
            if path.is_file() and path.suffix == "":
                stores.append(("mbox", path))
            elif path.is_dir() and (path / "cur").is_dir():
                stores.append(("maildir", path))

    unique: dict[str, tuple[str, Path]] = {}
    for kind, path in stores:
        unique[str(path.resolve())] = (kind, path.resolve())
    result = list(unique.values())
    if not result:
        raise AppError(
            "No se encontró la carpeta física Templates/Plantillas en el perfil. "
            "Use --templates-path /ruta/al/mbox_o_maildir."
        )
    return result


def ensure_email_message(message: Message) -> EmailMessage:
    return BytesParser(policy=policy.default).parsebytes(message.as_bytes())


def iter_store_messages(kind: str, path: Path) -> Iterator[tuple[int, EmailMessage]]:
    if kind == "mbox":
        box = mailbox.mbox(
            path,
            factory=lambda file_obj: BytesParser(policy=policy.default).parse(file_obj),
            create=False,
        )
    elif kind == "maildir":
        box = mailbox.Maildir(
            path,
            factory=lambda file_obj: BytesParser(policy=policy.default).parse(file_obj),
            create=False,
        )
    else:
        raise AppError(f"Tipo de almacén no soportado: {kind}")

    try:
        for index, message in enumerate(box):
            yield index, ensure_email_message(message)
    finally:
        box.close()


def message_timestamp(message: Message, fallback: float) -> float:
    raw_date = message.get("Date")
    if not raw_date:
        return fallback
    try:
        parsed = parsedate_to_datetime(str(raw_date))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return fallback


def attachment_names(message: Message) -> list[str]:
    names: list[str] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if disposition == "attachment" or filename:
            names.append(filename or f"adjunto-{len(names) + 1}")
    return names


def has_pdf_attachment(message: Message) -> bool:
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = (part.get_filename() or "").casefold()
        if part.get_content_type().casefold() == "application/pdf" or filename.endswith(".pdf"):
            return True
    return False


def extract_templates(stores: Iterable[tuple[str, Path]]) -> dict[str, TemplateCandidate]:
    wanted_by_subject = {normalize_text(subject): code for code, subject in TEMPLATE_SUBJECTS.items()}
    selected: dict[str, TemplateCandidate] = {}
    serial = 0
    for kind, path in stores:
        for position, message in iter_store_messages(kind, path):
            serial += 1
            subject = normalize_text(str(message.get("Subject", "")))
            code = wanted_by_subject.get(subject)
            if not code:
                continue
            candidate = TemplateCandidate(
                subject=subject,
                message=message,
                source=str(path),
                position=position,
                timestamp=message_timestamp(message, float(serial)),
                order=serial,
            )
            previous = selected.get(code)
            if previous is None or (candidate.timestamp, candidate.order) >= (
                previous.timestamp,
                previous.order,
            ):
                selected[code] = candidate

    missing = [code for code in TEMPLATE_SUBJECTS if code not in selected]
    if missing:
        expected = ", ".join(f"{code} → {TEMPLATE_SUBJECTS[code]!r}" for code in missing)
        raise AppError(f"Faltan plantillas de Thunderbird: {expected}")

    for code, candidate in selected.items():
        names = attachment_names(candidate.message)
        if not names:
            raise AppError(
                f"La plantilla {candidate.subject!r} no contiene adjuntos; se cancela la preparación."
            )
        if not has_pdf_attachment(candidate.message):
            raise AppError(
                f"La plantilla {candidate.subject!r} no contiene ningún PDF adjunto; se cancela."
            )
    return selected


def sender_from_message(message: Message) -> str:
    _, address = parseaddr(str(message.get("From", "")))
    address = address.strip()
    if not is_valid_email(address):
        raise AppError(
            f"La plantilla {message.get('Subject', '')!r} no tiene un encabezado From válido."
        )
    return address


def discover_smtp_settings(profile: Path, templates: dict[str, TemplateCandidate]) -> SmtpSettings:
    senders = {sender_from_message(candidate.message).casefold() for candidate in templates.values()}
    if len(senders) != 1:
        raise AppError(
            "Las tres plantillas usan remitentes distintos. Deben guardarse con la misma identidad "
            "de Thunderbird para utilizar una única configuración SMTP."
        )
    sender = next(iter(senders))
    prefs = parse_prefs_js(profile)

    identity_keys: list[str] = []
    for key, value in prefs.items():
        match = re.fullmatch(r"mail\.identity\.(id\d+)\.useremail", key)
        if match and str(value).strip().casefold() == sender:
            identity_keys.append(match.group(1))

    smtp_key = ""
    for identity_key in identity_keys:
        value = str(prefs.get(f"mail.identity.{identity_key}.smtpServer", "")).strip()
        if value:
            smtp_key = value
            break
    if not smtp_key:
        smtp_key = str(prefs.get("mail.smtp.defaultserver", "")).strip()

    smtp_keys = sorted(
        {
            match.group(1)
            for key in prefs
            if (match := re.fullmatch(r"mail\.smtpserver\.(smtp\d+)\.hostname", key))
        }
    )
    if not smtp_key and len(smtp_keys) == 1:
        smtp_key = smtp_keys[0]
    if not smtp_key:
        raise AppError(
            f"No se pudo determinar qué servidor SMTP utiliza la identidad {sender}."
        )

    prefix = f"mail.smtpserver.{smtp_key}."
    host = str(prefs.get(prefix + "hostname", "")).strip()
    username = str(prefs.get(prefix + "username", sender)).strip() or sender
    auth_method = int(prefs.get(prefix + "authMethod", 3))
    socket_type = int(prefs.get(prefix + "try_ssl", prefs.get(prefix + "socketType", 0)))
    port_value = prefs.get(prefix + "port", 0)
    try:
        port = int(port_value)
    except (TypeError, ValueError):
        port = 0

    security_by_socket = {0: "plain", 2: "starttls", 3: "ssl"}
    if socket_type not in security_by_socket:
        raise AppError(f"Tipo de seguridad SMTP no soportado en Thunderbird: {socket_type}")
    security = security_by_socket[socket_type]
    if not port:
        port = {"plain": 25, "starttls": 587, "ssl": 465}[security]
    if not host:
        raise AppError(f"El servidor {smtp_key} no tiene hostname en prefs.js")

    return SmtpSettings(
        sender_email=sender,
        host=host,
        port=port,
        security=security,
        username=username,
        auth_method=auth_method,
        smtp_key=smtp_key,
        profile_path=str(profile),
    )


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(content)
    os.replace(temp, path)


def prepare_state(profile_arg: Path | None, templates_path_arg: Path | None) -> None:
    profile = discover_thunderbird_profile(profile_arg)
    stores = discover_template_stores(profile, templates_path_arg)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_root = STATE_DIR / ".preparacion-temporal"
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root)
    snapshot_root.mkdir(parents=True, exist_ok=True)

    try:
        snapshot_stores = snapshot_template_stores(stores, snapshot_root)
        templates = extract_templates(snapshot_stores)
        smtp = discover_smtp_settings(profile, templates)
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    for code, candidate in templates.items():
        cache_path = TEMPLATES_DIR / TEMPLATE_CACHE_NAMES[code]
        atomic_write_bytes(cache_path, candidate.message.as_bytes(policy=policy.SMTP))

    smtp_payload = json.dumps(asdict(smtp), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    atomic_write_bytes(SMTP_STATE_FILE, smtp_payload)

    print(f"Perfil Thunderbird: {profile}")
    if thunderbird_is_running():
        print("Thunderbird permanece abierto: se utilizó una instantánea de solo lectura.")
    else:
        print("Thunderbird no estaba abierto: se utilizó igualmente una instantánea de solo lectura.")
    print("Plantillas preparadas:")
    for code, candidate in templates.items():
        names = ", ".join(attachment_names(candidate.message))
        print(f"  - {code}: {candidate.subject} [{names}]")
    print(f"Configuración SMTP: {smtp.host}:{smtp.port} ({smtp.security}), usuario {smtp.username}")
    if smtp.auth_method == 10:
        print(
            "Aviso: Thunderbird usa OAuth2. El script no extrae tokens ni contraseñas; "
            "para el envío deberá usar una contraseña de aplicación compatible en CVSENDER_SMTP_PASSWORD."
        )
    print(f"Estado guardado en: {STATE_DIR}")


def load_cached_templates() -> dict[str, EmailMessage]:
    templates: dict[str, EmailMessage] = {}
    missing: list[Path] = []
    for code, filename in TEMPLATE_CACHE_NAMES.items():
        path = TEMPLATES_DIR / filename
        if not path.is_file():
            missing.append(path)
            continue
        try:
            message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        except OSError as exc:
            raise AppError(f"No se pudo leer la plantilla preparada {path}: {exc}") from exc
        expected_subject = TEMPLATE_SUBJECTS[code]
        actual_subject = normalize_text(str(message.get("Subject", "")))
        if actual_subject != expected_subject:
            raise AppError(
                f"La plantilla preparada {path} tiene asunto {actual_subject!r}; "
                f"se esperaba {expected_subject!r}. Ejecute --preparar nuevamente."
            )
        if not has_pdf_attachment(message):
            raise AppError(
                f"La plantilla preparada {path} no contiene un PDF. Ejecute --preparar nuevamente."
            )
        templates[code] = message
    if missing:
        raise AppError(
            "No están preparadas todas las plantillas. Ejecute primero: "
            "python3 cvsender.py --preparar"
        )
    return templates


def load_smtp_settings(args: argparse.Namespace) -> SmtpSettings:
    if not SMTP_STATE_FILE.is_file():
        raise AppError(
            "No existe la configuración SMTP preparada. Ejecute primero: "
            "python3 cvsender.py --preparar"
        )
    try:
        data = json.loads(SMTP_STATE_FILE.read_text(encoding="utf-8"))
        settings = SmtpSettings(**data)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise AppError(
            f"No se pudo leer {SMTP_STATE_FILE}. Ejecute --preparar nuevamente: {exc}"
        ) from exc

    return SmtpSettings(
        sender_email=settings.sender_email,
        host=args.smtp_host or settings.host,
        port=args.smtp_port or settings.port,
        security=args.smtp_security or settings.security,
        username=args.smtp_user or settings.username,
        auth_method=settings.auth_method,
        smtp_key=settings.smtp_key,
        profile_path=settings.profile_path,
    )


def is_valid_email(value: str) -> bool:
    if not value or value != value.strip():
        return False
    display_name, parsed = parseaddr(value)
    if display_name or parsed != value:
        return False
    return bool(EMAIL_RE.fullmatch(value))


def read_csv_entries(path: Path, allow_duplicates: bool) -> list[CsvEntry]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise AppError(f"No existe el CSV: {path}")

    try:
        file_obj = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise AppError(f"No se pudo abrir el CSV {path}: {exc}") from exc

    entries: list[CsvEntry] = []
    errors: list[str] = []
    seen_emails: dict[str, int] = {}
    with file_obj:
        reader = csv.DictReader(file_obj)
        if reader.fieldnames != CSV_HEADERS:
            raise AppError(
                "Encabezado CSV inválido. Debe ser exactamente:\n"
                + ",".join(CSV_HEADERS)
                + f"\nRecibido: {reader.fieldnames}"
            )

        for line_number, row in enumerate(reader, start=2):
            cleaned = {key: normalize_text(row.get(key, "")) for key in CSV_HEADERS}
            blank_fields = [key for key, value in cleaned.items() if not value]
            if blank_fields:
                errors.append(f"línea {line_number}: campos vacíos: {', '.join(blank_fields)}")
                continue

            email = cleaned["correo"]
            if not is_valid_email(email):
                errors.append(f"línea {line_number}: correo inválido: {email!r}")
                continue

            language = cleaned["idioma_recomendado"]
            if language not in TEMPLATE_SUBJECTS:
                errors.append(
                    f"línea {line_number}: idioma_recomendado inválido: {language!r}"
                )
                continue

            email_key = email.casefold()
            if not allow_duplicates and email_key in seen_emails:
                errors.append(
                    f"línea {line_number}: correo duplicado; ya apareció en la línea "
                    f"{seen_emails[email_key]}: {email}"
                )
                continue
            seen_emails[email_key] = line_number

            entries.append(
                CsvEntry(
                    line_number=line_number,
                    organizacion_o_reparticion=cleaned["organizacion_o_reparticion"],
                    puesto_o_area_recomendada=cleaned["puesto_o_area_recomendada"],
                    idioma_recomendado=language,
                    correo=email,
                    recomendacion=cleaned["recomendacion"],
                )
            )

    if errors:
        raise AppError("El CSV no pasó la validación:\n- " + "\n- ".join(errors))
    return entries


def remove_header_all(message: Message, header_name: str) -> None:
    while header_name in message:
        del message[header_name]


def build_message(template: EmailMessage, recipient: str) -> EmailMessage:
    message = deepcopy(template)

    for header_name in list(dict.fromkeys(message.keys())):
        lower = header_name.casefold()
        if lower in DROP_HEADERS or lower.startswith("x-mozilla-") or lower in {
            "x-account-key",
            "x-identity-key",
        }:
            remove_header_all(message, header_name)

    message["To"] = recipient
    message["Date"] = formatdate(localtime=True)
    sender = sender_from_message(message)
    domain = sender.rsplit("@", 1)[1]
    message["Message-ID"] = make_msgid(domain=domain)
    return message


def safe_filename_component(value: str, max_length: int = 70) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r"[^A-Za-z0-9._@+-]+", "_", value).strip("._")
    return (value or "mensaje")[:max_length]


def message_digest(message: EmailMessage) -> str:
    return hashlib.sha256(message.as_bytes(policy=policy.SMTP)).hexdigest()[:12]


def archive_message(
    message: EmailMessage,
    entry: CsvEntry,
    archive_root: Path,
    category: str,
) -> Path:
    now = datetime.now().astimezone()
    day_dir = archive_root.expanduser() / category / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    digest = message_digest(message)
    filename = (
        f"{now.strftime('%H%M%S_%f')}_"
        f"{safe_filename_component(entry.correo)}_"
        f"{safe_filename_component(entry.idioma_recomendado)}_{digest}.eml"
    )
    path = day_dir / filename
    path.write_bytes(message.as_bytes(policy=policy.SMTP))
    return path


def move_archive(path: Path, archive_root: Path, category: str) -> Path:
    day = path.parent.name
    destination_dir = archive_root.expanduser() / category / day
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / path.name
    return Path(shutil.move(str(path), str(destination)))


def append_log(
    log_path: Path,
    entry: CsvEntry,
    template_subject: str,
    status: str,
    detail: str,
    eml_path: Path | None,
) -> None:
    headers = [
        "fecha_hora",
        *CSV_HEADERS,
        "plantilla_thunderbird",
        "estado",
        "detalle",
        "archivo_eml",
    ]
    row = {
        "fecha_hora": datetime.now().astimezone().isoformat(timespec="seconds"),
        "organizacion_o_reparticion": entry.organizacion_o_reparticion,
        "puesto_o_area_recomendada": entry.puesto_o_area_recomendada,
        "idioma_recomendado": entry.idioma_recomendado,
        "correo": entry.correo,
        "recomendacion": entry.recomendacion,
        "plantilla_thunderbird": template_subject,
        "estado": status,
        "detalle": detail,
        "archivo_eml": str(eml_path) if eml_path else "",
    }

    log_path = log_path.expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not log_path.exists() or log_path.stat().st_size == 0
    with log_path.open("a", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=headers, quoting=csv.QUOTE_ALL)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


class SmtpConnection:
    def __init__(
        self,
        settings: SmtpSettings,
        password: str | None,
        timeout: float,
        debug: bool,
    ) -> None:
        self.settings = settings
        self.password = password
        self.timeout = timeout
        self.debug = debug
        self.client: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    def connect(self) -> None:
        context = ssl.create_default_context()
        client: smtplib.SMTP | smtplib.SMTP_SSL | None = None
        try:
            if self.settings.security == "ssl":
                client = smtplib.SMTP_SSL(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.timeout,
                    context=context,
                )
            else:
                client = smtplib.SMTP(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.timeout,
                )
                if self.debug:
                    client.set_debuglevel(1)
                client.ehlo()
                if self.settings.security == "starttls":
                    client.starttls(context=context)
                    client.ehlo()

            if self.debug and self.settings.security == "ssl":
                client.set_debuglevel(1)
            if self.settings.auth_method != 1:
                if not self.settings.username:
                    raise AppError(
                        "La configuración SMTP requiere autenticación, pero no tiene usuario."
                    )
                if self.password is None:
                    raise AppError("La configuración SMTP requiere contraseña.")
                client.login(self.settings.username, self.password)
            self.client = client
        except Exception:
            if client is not None:
                try:
                    client.close()
                except OSError:
                    pass
            raise

    def close(self) -> None:
        if self.client is None:
            return
        try:
            self.client.quit()
        except (smtplib.SMTPException, OSError):
            try:
                self.client.close()
            except OSError:
                pass
        finally:
            self.client = None

    def send(self, message: EmailMessage, recipient: str) -> None:
        if self.client is None:
            self.connect()
        assert self.client is not None
        sender = sender_from_message(message)
        try:
            self.client.send_message(message, from_addr=sender, to_addrs=[recipient])
        except smtplib.SMTPServerDisconnected:
            self.close()
            self.connect()
            assert self.client is not None
            self.client.send_message(message, from_addr=sender, to_addrs=[recipient])

    def __enter__(self) -> "SmtpConnection":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def get_smtp_password(settings: SmtpSettings, env_name: str) -> str | None:
    if settings.auth_method == 1:
        return None
    password = os.environ.get(env_name)
    if password is not None:
        return password
    prompt = f"Contraseña SMTP para {settings.username} en {settings.host}: "
    return getpass.getpass(prompt)


def apply_smtp_overrides(settings: SmtpSettings, args: argparse.Namespace) -> SmtpSettings:
    security = args.smtp_security or settings.security
    port = args.smtp_port or settings.port
    if args.smtp_security and not args.smtp_port:
        port = {"plain": 25, "starttls": 587, "ssl": 465}[security]
    return SmtpSettings(
        sender_email=settings.sender_email,
        host=args.smtp_host or settings.host,
        port=port,
        security=security,
        username=args.smtp_user or settings.username,
        auth_method=settings.auth_method,
        smtp_key=settings.smtp_key,
        profile_path=settings.profile_path,
    )


def send_entries(args: argparse.Namespace) -> int:
    entries = read_csv_entries(args.csv, args.permitir_duplicados)
    if not entries:
        print("El CSV no contiene filas de datos. No hay correos para enviar.")
        return 0

    templates = load_cached_templates()
    smtp = apply_smtp_overrides(load_smtp_settings(args), args)

    # Verificación final antes de abrir SMTP: cada plantilla sigue usando el remitente preparado.
    for code, template in templates.items():
        sender = sender_from_message(template).casefold()
        if sender != smtp.sender_email.casefold():
            raise AppError(
                f"La plantilla {TEMPLATE_SUBJECTS[code]!r} usa {sender}, pero la preparación "
                f"SMTP corresponde a {smtp.sender_email}. Ejecute --preparar nuevamente."
            )

    print(f"CSV: {args.csv.expanduser().resolve()}")
    print(f"Filas válidas: {len(entries)}")
    for code in TEMPLATE_SUBJECTS:
        count = sum(entry.idioma_recomendado == code for entry in entries)
        if count:
            print(f"  - {code} → {TEMPLATE_SUBJECTS[code]}: {count}")

    password: str | None = None
    connection: SmtpConnection | None = None
    if not args.dry_run:
        password = get_smtp_password(smtp, args.smtp_password_env)
        connection = SmtpConnection(smtp, password, args.timeout, args.debug_smtp)
        print(f"SMTP: {smtp.host}:{smtp.port} ({smtp.security})")
    else:
        print("Modo dry-run: no se establecerá conexión SMTP.")

    success = 0
    failures = 0
    try:
        if connection is not None:
            try:
                connection.connect()
            except (smtplib.SMTPException, OSError, AppError) as exc:
                raise AppError(f"No se pudo iniciar la sesión SMTP: {exc}") from exc

        for index, entry in enumerate(entries, start=1):
            template = templates[entry.idioma_recomendado]
            subject = TEMPLATE_SUBJECTS[entry.idioma_recomendado]
            message = build_message(template, entry.correo)
            eml_path: Path | None = None

            if args.dry_run:
                try:
                    eml_path = archive_message(
                        message, entry, args.archive_dir, category="dry-run"
                    )
                    append_log(
                        args.log,
                        entry,
                        subject,
                        "GENERADO",
                        "Mensaje generado sin envío",
                        eml_path,
                    )
                    success += 1
                    print(f"[{index}/{len(entries)}] GENERADO: {entry.correo} ← {subject}")
                except OSError as exc:
                    failures += 1
                    detail = f"{type(exc).__name__}: {exc}"
                    append_log(args.log, entry, subject, "ERROR", detail, eml_path)
                    eprint(f"[{index}/{len(entries)}] ERROR: {entry.correo}: {exc}")
            else:
                try:
                    eml_path = archive_message(
                        message, entry, args.archive_dir, category="pendientes"
                    )
                except OSError as exc:
                    failures += 1
                    detail = f"No se pudo archivar el mensaje antes del envío: {exc}"
                    append_log(args.log, entry, subject, "ERROR", detail, None)
                    eprint(f"[{index}/{len(entries)}] ERROR: {entry.correo}: {detail}")
                    if index < len(entries) and args.delay:
                        time.sleep(args.delay)
                    continue

                try:
                    assert connection is not None
                    connection.send(message, entry.correo)
                except (smtplib.SMTPException, OSError, AppError) as exc:
                    failures += 1
                    try:
                        eml_path = move_archive(eml_path, args.archive_dir, "errores")
                    except OSError:
                        pass
                    detail = f"{type(exc).__name__}: {exc}"
                    append_log(args.log, entry, subject, "ERROR", detail, eml_path)
                    eprint(f"[{index}/{len(entries)}] ERROR: {entry.correo}: {exc}")
                else:
                    detail = "SMTP aceptó el mensaje"
                    try:
                        eml_path = move_archive(eml_path, args.archive_dir, "enviados")
                    except OSError as exc:
                        detail += f"; no se pudo mover el archivo EML: {exc}"
                    append_log(args.log, entry, subject, "ENVIADO", detail, eml_path)
                    success += 1
                    print(f"[{index}/{len(entries)}] ENVIADO: {entry.correo} ← {subject}")

            if index < len(entries) and args.delay:
                time.sleep(args.delay)
    finally:
        if connection is not None:
            connection.close()

    print(f"Completado. Correctos: {success}. Errores: {failures}.")
    print(f"Registro: {args.log.expanduser()}")
    print(f"Archivo EML: {args.archive_dir.expanduser()}")
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.preparar:
            prepare_state(args.profile, args.templates_path)
            return 0
        return send_entries(args)
    except AppError as exc:
        eprint(f"ERROR: {exc}")
        return 2
    except (OSError, smtplib.SMTPException) as exc:
        eprint(f"ERROR: {type(exc).__name__}: {exc}")
        return 2
    except KeyboardInterrupt:
        eprint("\nOperación cancelada por el usuario.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
