"""Protocol constants of the Teleco cloud and of the Daisy box."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# --- Cloud -----------------------------------------------------------------

BASE_URL: Final = "https://tmate.telecoautomation.com"
BASE_URL_STAGE: Final = "https://stage.tmate.telecoautomation.com"

# Static HTTP basic auth sent on every request (TMateApiClient.USERNAME/PASSWORD).
BASIC_AUTH_USER: Final = "teleco"
BASIC_AUTH_PASSWORD: Final = "tmate20"

DEFAULT_DEVICE_SERIAL: Final = "0000000000000000"
DEFAULT_DEVICE_DESCRIPTION: Final = "aioteleco"

# Envelope values.
ESITO_OK: Final = "S"
MSG_SESSION_NOT_VALID: Final = "Session not valid"
MSG_WRONG_CREDENTIALS: Final = "Wrong user name or password"
MSG_REGISTRATION_NOT_CONFIRMED: Final = "Request User registration not confirm"
TMATE_MESSAGE_TYPE_OK: Final = "INFO"

# getackcommand MessageText values the app reacts to.
ACK_PROCESSED: Final = "PROC"
ACK_ACCEPTED: Final = "ACK"
ACK_POLL_INTERVAL: Final = 0.5


class Endpoint(StrEnum):
    """Cloud endpoints (TMateCloudApi). All are JSON POSTs."""

    ACCOUNT_LOGIN = "teleco/services/account-login"
    ACCOUNT_LOGOUT = "teleco/services/account-logout"
    ACCOUNT_REGISTRATION = "teleco/services/account-registration"
    CHANGE_PASSWORD = "teleco/services/change-password"
    RESET_PASSWORD = "teleco/services/reset-password"
    INSTALLATION_LIST = "teleco/services/account-installation-list"
    INSTALLATION_PAIR = "teleco/services/account-installation-pair"
    INSTALLATION_UNPAIR = "teleco/services/account-installation-unpair"
    INSTALLATION_SETUP = "teleco/services/installation-setup"
    ROOM_LIST = "teleco/services/room-list"
    ROOM_CONFIGURATION_LIST = "teleco/services/room-configuration-list"
    ROOM_SETUP = "teleco/services/room-setup"
    ROOM_DELETE = "teleco/services/room-delete"
    SCENARIO_LIST = "teleco/services/scenario-list"
    SCENARIO_SETUP = "teleco/services/scenario-setup"
    SCENARIO_DELETE = "teleco/services/scenario-delete"
    COMMAND_DEVICE_LIST = "teleco/services/command-device-list"
    COMMAND_SCENARIO_LIST = "teleco/services/command-scenario-list"
    STATUS_DEVICE_LIST = "teleco/services/status-device-list"
    TIMER_DEVICE_LIST = "teleco/services/timer-device-list/"
    TIMER_DEVICE_SETUP = "teleco/services/timer-device-setup/"
    FEED_THE_COMMANDS = "teleco/services/tmate20/feedthecommands/"
    GET_ACK_COMMAND = "teleco/services/tmate20/getackcommand/"
    NODE_STATUS = "teleco/services/tmate20/nodestatus/"


# --- Local (LAN) channel -----------------------------------------------------

LOCAL_PORT: Final = 400
LOCAL_CONNECT_TIMEOUT: Final = 0.5
LOCAL_READ_TIMEOUT: Final = 5.0
LOCAL_READ_TIMEOUT_SCENARIO: Final = 10.0
LOCAL_READ_TIMEOUT_CHANNEL: Final = 2.0
LOCAL_ACK: Final = "ACK"

# --- Commands ----------------------------------------------------------------

SYSTEM_COMMAND_ID: Final = 122


class CommandAction(StrEnum):
    """Values of `commandAction` sent by the app's device screens."""

    POWER = "POWER"
    LEVEL = "LEVEL"
    OPEN_STOP_CLOSE = "OPEN_STOP_CLOSE"
    COLOR = "COLOR"
    CYCLE = "CYCLE"
    SPEED = "SPEED"
    CHANNEL = "CHANNEL"
    PAUSE_PLAY = "PAUSE_PLAY"
    AUDIO_ACTION = "AUDIO_ACTION"


class StatusItemCode(StrEnum):
    """Status items returned by status-device-list (`statusItem`)."""

    POWER = "POWER"
    LEVEL = "LEVEL"
    OPEN_CLOSE = "OPEN_CLOSE"
    RETR = "RETR"
    COLOR = "COLOR"
    CYCLE = "CYCLE"
    SPEED = "SPEED"
    AUDIO_PLAY_PAUSE = "AUDIO_PLAY_PAUSE"
    # Box-level items
    NET_PARAM = "NET_PARAM"
    SIGNAL = "SIGNAL"
    CURRENT_TIME = "CURRENT_TIME"
    DIAGNOSTIC = "DIAGNOSTIC"
    UPDATE_STATUS = "UPDATE_STATUS"
    PAIRING_STATUS = "PAIRING_STATUS"
    TX_NUM = "TX_NUM"
