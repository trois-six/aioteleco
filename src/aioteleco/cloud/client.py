"""Low-level HTTP client for the Teleco "tmate" cloud.

Every endpoint is a JSON POST protected by a static basic auth. The user session
(`idSession` + `idAccount`) travels inside the JSON body. Two response formats
exist:

* the standard envelope ``{codEsito, msgEsito, valRisultato}``;
* the ``tmate20/*`` format ``{MessageType, MessageID, MessageText, ActionReference}``
  (``nodestatus`` returns a bare object).
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aiohttp

from ..const import (
    BASE_URL,
    BASIC_AUTH_PASSWORD,
    BASIC_AUTH_USER,
    DEFAULT_DEVICE_DESCRIPTION,
    DEFAULT_DEVICE_SERIAL,
    ESITO_OK,
    MSG_REGISTRATION_NOT_CONFIRMED,
    MSG_SESSION_NOT_VALID,
    MSG_WRONG_CREDENTIALS,
    TMATE_MESSAGE_TYPE_OK,
    Endpoint,
)
from ..exceptions import (
    TelecoApiError,
    TelecoAuthError,
    TelecoConnectionError,
    TelecoSessionExpiredError,
)

_LOGGER = logging.getLogger(__name__)

JsonDict = dict[str, Any]


class SessionFields(Enum):
    """Which session fields a request body carries."""

    NONE = "none"
    SESSION = "session"  # idSession only (tmate20/*, logout)
    ACCOUNT = "account"  # idSession + idAccount


@dataclass(slots=True)
class CloudSession:
    id_session: str
    id_account: int


@dataclass(slots=True, frozen=True)
class TmateResponse:
    """Response of feedthecommands / getackcommand."""

    message_type: str | None
    message_id: str | None
    message_text: str | None
    action_reference: str | None

    @property
    def ok(self) -> bool:
        return self.message_type == TMATE_MESSAGE_TYPE_OK

    @classmethod
    def from_json(cls, data: JsonDict) -> TmateResponse:
        return cls(
            message_type=data.get("MessageType"),
            message_id=data.get("MessageID"),
            message_text=data.get("MessageText"),
            action_reference=data.get("ActionReference"),
        )


class CloudClient:
    """Authenticated access to the Teleco cloud.

    The ``aiohttp.ClientSession`` is injected (Home Assistant provides its own) and
    is never closed by this class.
    """

    def __init__(
        self,
        http: aiohttp.ClientSession,
        email: str,
        password: str,
        *,
        base_url: str = BASE_URL,
        device_serial: str = DEFAULT_DEVICE_SERIAL,
        device_description: str = DEFAULT_DEVICE_DESCRIPTION,
        request_timeout: float = 15.0,
        auto_relogin: bool = True,
    ) -> None:
        self._http = http
        self._email = email
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._device_serial = device_serial
        self._device_description = device_description
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        credentials = base64.b64encode(f"{BASIC_AUTH_USER}:{BASIC_AUTH_PASSWORD}".encode())
        self._headers = {"Authorization": f"Basic {credentials.decode()}"}
        self._auto_relogin = auto_relogin
        self._login_lock = asyncio.Lock()
        self.session: CloudSession | None = None

    # -- session -------------------------------------------------------------

    @property
    def id_account(self) -> int:
        return self._require_session().id_account

    async def login(self) -> CloudSession:
        """Open a new cloud session (account-login)."""
        body = {
            "email": self._email,
            "pwd": self._password,
            "deviceSerial": self._device_serial,
            "deviceDescription": self._device_description,
        }
        data = await self._post_json(Endpoint.ACCOUNT_LOGIN, body)
        msg = data.get("msgEsito")
        if data.get("codEsito") != ESITO_OK or msg == MSG_REGISTRATION_NOT_CONFIRMED:
            raise TelecoAuthError(msg or MSG_WRONG_CREDENTIALS)
        result = data.get("valRisultato") or {}
        try:
            self.session = CloudSession(
                id_session=str(result["idSession"]), id_account=int(result["idAccount"])
            )
        except (KeyError, TypeError, ValueError) as err:
            raise TelecoAuthError(f"login succeeded without a session: {data!r}") from err
        return self.session

    async def logout(self) -> None:
        if self.session is None:
            return
        try:
            await self.call(Endpoint.ACCOUNT_LOGOUT, {}, fields=SessionFields.SESSION)
        finally:
            self.session = None

    async def ensure_session(self) -> CloudSession:
        if self.session is not None:
            return self.session
        async with self._login_lock:
            if self.session is None:
                await self.login()
            return self._require_session()

    def _require_session(self) -> CloudSession:
        if self.session is None:
            raise TelecoSessionExpiredError("Not logged in")
        return self.session

    async def _relogin(self, stale: CloudSession) -> None:
        async with self._login_lock:
            if self.session is stale or self.session is None:
                self.session = None
                await self.login()

    # -- requests ------------------------------------------------------------

    async def call(
        self,
        endpoint: Endpoint | str,
        body: JsonDict,
        *,
        fields: SessionFields = SessionFields.ACCOUNT,
    ) -> Any:
        """POST to a standard-envelope endpoint and return ``valRisultato``.

        Session fields are injected; an invalid session triggers one re-login.
        """
        data = await self.call_raw(endpoint, body, fields=fields)
        if data.get("codEsito") != ESITO_OK:
            raise TelecoApiError(
                data.get("msgEsito") or "Unknown cloud error",
                code=data.get("codEsito"),
                payload=data,
            )
        return data.get("valRisultato")

    async def call_raw(
        self,
        endpoint: Endpoint | str,
        body: JsonDict,
        *,
        fields: SessionFields = SessionFields.ACCOUNT,
    ) -> JsonDict:
        """POST and return the raw JSON object, handling session expiry."""
        if fields is SessionFields.NONE:
            return await self._post_json(endpoint, body)
        session = await self.ensure_session()
        data = await self._post_json(endpoint, self._with_session(body, session, fields))
        if self._auto_relogin and self._is_session_invalid(data):
            _LOGGER.debug("Cloud session expired, logging in again")
            await self._relogin(session)
            session = self._require_session()
            data = await self._post_json(endpoint, self._with_session(body, session, fields))
            if self._is_session_invalid(data):
                raise TelecoSessionExpiredError(MSG_SESSION_NOT_VALID)
        return data

    async def call_tmate(self, endpoint: Endpoint | str, body: JsonDict) -> TmateResponse:
        """POST to a ``tmate20/*`` command endpoint."""
        return TmateResponse.from_json(
            await self.call_raw(endpoint, body, fields=SessionFields.SESSION)
        )

    @staticmethod
    def _with_session(body: JsonDict, session: CloudSession, fields: SessionFields) -> JsonDict:
        out = dict(body)
        out["idSession"] = session.id_session
        if fields is SessionFields.ACCOUNT:
            out["idAccount"] = session.id_account
        return out

    @staticmethod
    def _is_session_invalid(data: JsonDict) -> bool:
        return data.get("msgEsito") == MSG_SESSION_NOT_VALID

    async def _post_json(self, endpoint: Endpoint | str, body: JsonDict) -> JsonDict:
        url = f"{self._base_url}/{str(endpoint).lstrip('/')}"
        try:
            async with self._http.post(
                url, json=body, headers=self._headers, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TelecoConnectionError(f"{endpoint}: {err}") from err
        except ValueError as err:  # not JSON (e.g. an HTML error page)
            raise TelecoApiError(f"{endpoint}: invalid JSON response") from err
        if not isinstance(data, dict):
            raise TelecoApiError(f"{endpoint}: unexpected response", payload=data)
        return data
