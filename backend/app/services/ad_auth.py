"""Active Directory (LDAPS) password check, following the admin's AGMK LDAPS guide.

Rules that must not be weakened:
- LDAPS only (port 636); the CA file and the server NAME are always verified.
- An empty password never reaches LDAP (AD treats it as a successful anonymous bind).
- Failover to the second domain controller happens ONLY on network/TLS errors,
  never after "wrong password" (every attempt counts toward AD's account lock).
- After a successful bind the identity is read with "Who am I?" and the entry is
  looked up by sAMAccountName, never by the typed login (userPrincipalName tricks).
- No password is stored or logged.
"""
import logging
import re
import ssl
import uuid
from dataclasses import dataclass

import ldap3
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.core.config import settings

logger = logging.getLogger(__name__)

LOGIN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
INVALID_CREDENTIALS = 49


class AdRejected(Exception):
    """The domain says the login/password is wrong (or the account is unusable)."""

    def __init__(self, ad_code: str | None = None) -> None:
        super().__init__("ad rejected")
        self.ad_code = ad_code


class AdUnavailable(Exception):
    """No domain controller could be used (network, TLS, unexpected answer)."""


@dataclass(frozen=True)
class AdIdentity:
    guid: str
    login: str
    name: str | None
    mail: str | None


def is_valid_login(login: str) -> bool:
    return LOGIN_RE.fullmatch(login) is not None


def _first(attributes, name: str):
    value = attributes.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value or None


def _ad_error_code(message: str | None) -> str | None:
    match = re.search(r"data ([0-9a-fA-F]{3})", message or "")
    return match.group(1).lower() if match else None


def _check_one_server(host: str, login: str, password: str) -> AdIdentity:
    tls = ldap3.Tls(
        validate=ssl.CERT_REQUIRED,  # ldap3's default Tls() verifies nothing
        ca_certs_file=settings.ad_ca_file,
        version=ssl.PROTOCOL_TLS_CLIENT,
    )
    server = ldap3.Server(
        host,
        port=636,
        use_ssl=True,
        tls=tls,
        get_info=ldap3.NONE,
        connect_timeout=int(settings.ad_connect_timeout),
    )
    conn = ldap3.Connection(
        server,
        user=f"{login}@{settings.ad_domain}",
        password=password,
        authentication=ldap3.SIMPLE,
        receive_timeout=int(settings.ad_receive_timeout),  # must be an int on Linux
        auto_referrals=False,
        raise_exceptions=False,
    )
    try:
        if not conn.bind():
            result = conn.result or {}
            if result.get("result") == INVALID_CREDENTIALS:
                raise AdRejected(_ad_error_code(result.get("message")))
            logger.warning("AD bind failed with unexpected LDAP result %s", result.get("result"))
            raise AdUnavailable()
        authz = conn.extend.standard.who_am_i() or ""  # "u:AGMK\\login"
        if not authz.startswith("u:") or "\\" not in authz:
            raise AdRejected()
        bound = authz.rsplit("\\", 1)[1]
        conn.search(
            settings.ad_base_dn,
            "(&(objectCategory=person)(objectClass=user)"
            f"(sAMAccountName={escape_filter_chars(bound)}))",
            search_scope=ldap3.SUBTREE,
            attributes=["objectGUID", "sAMAccountName", "displayName", "mail"],
            size_limit=2,
        )
        found = [r for r in conn.response or [] if r.get("type") == "searchResEntry"]
        if len(found) != 1:
            raise AdRejected()
        raw, attrs = found[0]["raw_attributes"], found[0]["attributes"]
        return AdIdentity(
            guid=str(uuid.UUID(bytes_le=raw["objectGUID"][0])),
            login=str(_first(attrs, "sAMAccountName") or bound),
            name=_first(attrs, "displayName"),
            mail=_first(attrs, "mail"),
        )
    finally:
        try:
            conn.unbind()
        except Exception:  # noqa: BLE001 - closing must never mask the real result
            pass


def verify_password(login: str, password: str) -> AdIdentity:
    """Return the AD identity when the password is right.

    Raises AdRejected for a wrong password/unusable account and AdUnavailable
    when no domain controller answered. Blocking: call it in a thread pool.
    """
    if not is_valid_login(login) or not password.strip():
        raise AdRejected()
    hosts = [h.strip() for h in settings.ad_servers.split(",") if h.strip()]
    for host in hosts:
        try:
            identity = _check_one_server(host, login, password)
            # The guide's userPrincipalName trap: AD may bind a DIFFERENT account
            # than the typed login (an account whose UPN equals this login). The
            # password must open exactly the account that was typed.
            if identity.login.casefold() != login.casefold():
                logger.warning(
                    "AD bound account %r differs from typed login %r: rejected",
                    identity.login,
                    login,
                )
                raise AdRejected("login-mismatch")
            return identity
        except AdRejected:
            raise  # never retry another DC after a wrong password
        except (AdUnavailable, LDAPException, OSError, ssl.SSLError) as exc:
            logger.warning(
                "AD server %s unavailable (%s)", host, type(exc).__name__
            )
            continue
    raise AdUnavailable()
