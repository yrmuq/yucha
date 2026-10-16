# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Start mpv immediately, and open the Syncplay connection on demand.

SyncplayClient.start() also calls reactor.run(). yucha runs the reactor
itself and only copies the network half, so a failed login does not close
the window.
"""

import hashlib
import os
import shutil
from pathlib import Path

from twisted.application.internet import ClientService
from twisted.internet import reactor
from twisted.internet.endpoints import HostnameEndpoint

from syncplay import constants
from syncplay.client import SSL_CERT_FILE, SyncClientFactory, SyncplayClient
from syncplay.messages import getMessage, setLanguage
from syncplay.players.mpv import MpvPlayer


ROOT = Path(__file__).resolve().parents[1]


def _defaults():
    return {
        "host": None,
        "port": constants.DEFAULT_PORT,
        "name": None,
        "debug": False,
        "forceGuiPrompt": False,
        "noGui": True,
        "noStore": True,
        "room": "",
        "roomList": [],
        "password": None,
        "playerPath": None,
        "perPlayerArguments": None,
        "mediaSearchDirectories": None,
        "sharedPlaylistEnabled": True,
        "loopAtEndOfPlaylist": False,
        "loopSingleFiles": False,
        "onlySwitchToTrustedDomains": True,
        "autosaveJoinsToList": False,
        "trustedDomains": constants.DEFAULT_TRUSTED_DOMAINS,
        "file": None,
        "playerArgs": [],
        "playerClass": MpvPlayer,
        "slowdownThreshold": constants.DEFAULT_SLOWDOWN_KICKIN_THRESHOLD,
        "rewindThreshold": constants.DEFAULT_REWIND_THRESHOLD,
        "fastforwardThreshold": constants.DEFAULT_FASTFORWARD_THRESHOLD,
        "rewindOnDesync": True,
        "slowOnDesync": True,
        "fastforwardOnDesync": True,
        "dontSlowDownWithMe": False,
        "folderSearchFirstFileTimeout": constants.FOLDER_SEARCH_FIRST_FILE_TIMEOUT,
        "folderSearchTimeout": constants.FOLDER_SEARCH_TIMEOUT,
        "folderSearchDoubleCheckInterval": constants.FOLDER_SEARCH_DOUBLE_CHECK_INTERVAL,
        "folderSearchWarningThreshold": constants.FOLDER_SEARCH_WARNING_THRESHOLD,
        "filenamePrivacyMode": constants.PRIVACY_SENDRAW_MODE,
        "filesizePrivacyMode": constants.PRIVACY_SENDRAW_MODE,
        "pauseOnLeave": False,
        "readyAtStart": False,
        "unpauseAction": constants.UNPAUSE_IFOTHERSREADY_MODE,
        "autoplayInitialState": None,
        "autoplayMinUsers": -1,
        "autoplayRequireSameFilenames": True,
        "clearGUIData": False,
        "language": "en",
        "checkForUpdatesAutomatically": False,
        "lastCheckedForUpdates": "",
        "resetConfig": False,
        "watchedSubfolder": "Watched",
        "watchedSubfolderAutocreate": False,
        "watchedAutoMove": False,
        "watchedHistoryEnabled": False,
        "autoRemoveWatchedFromPlaylist": False,
        "configDir": "",
        "showOSD": False,
        "showOSDWarnings": False,
        "showSlowdownOSD": False,
        "showDifferentRoomOSD": False,
        "showSameRoomOSD": False,
        "showNonControllerOSD": False,
        "showContactInfo": False,
        "showDurationNotification": False,
        "showPlaylistSkipWarnings": False,
        "showPlaylistOrderWarnings": False,
        "chatInputEnabled": False,
        "chatInputFontFamily": "sans-serif",
        "chatInputRelativeFontSize": constants.DEFAULT_CHAT_FONT_SIZE,
        "chatInputFontWeight": constants.DEFAULT_CHAT_FONT_WEIGHT,
        "chatInputFontUnderline": False,
        "chatInputFontColor": constants.DEFAULT_CHAT_INPUT_FONT_COLOR,
        "chatInputPosition": constants.INPUT_POSITION_TOP,
        "chatDirectInput": False,
        "chatOutputEnabled": False,
        "chatOutputFontFamily": "sans-serif",
        "chatOutputRelativeFontSize": constants.DEFAULT_CHAT_FONT_SIZE,
        "chatOutputFontWeight": constants.DEFAULT_CHAT_FONT_WEIGHT,
        "chatOutputFontUnderline": False,
        "chatOutputMode": constants.CHATROOM_MODE,
        "chatMaxLines": 7,
        "chatTopMargin": 25,
        "chatLeftMargin": 20,
        "chatBottomMargin": 30,
        "chatMoveOSD": False,
        "chatOSDMargin": 110,
        "notificationTimeout": 3,
        "alertTimeout": 5,
        "chatTimeout": 7,
        "publicServers": [],
        "loadPlaylistFromFile": None,
        "configPath": "",
    }


def mpv_path():
    chosen = os.environ.get("YUCHA_MPV") or shutil.which("mpv")
    if not chosen:
        raise SystemExit(
            "yucha needs an mpv binary on PATH, or YUCHA_MPV=/path/to/mpv.\n"
            "Upstream source is in third_party/mpv (not compiled by this launcher)."
        )
    return chosen


def player_args(runtime):
    script = ROOT / "ui" / "mpv" / "yucha.lua"
    intf = ROOT / "third_party" / "syncplay" / "syncplay" / "resources" / "syncplayintf.lua"
    opts = "yucha-syncplayintf={0},yucha-runtime={1}".format(intf, runtime)
    args = [
        "--script={0}".format(script),
        "--script-opts={0}".format(opts),
        "--osc=no",
        "--geometry=1280x720",
    ]
    vo = os.environ.get("YUCHA_VO")
    if vo:
        args.append("--vo={0}".format(vo))
    ao = os.environ.get("YUCHA_AO")
    if ao:
        args.append("--ao={0}".format(ao))
    log_path = os.environ.get("YUCHA_LOG")
    if log_path:
        args.append("--log-file={0}".format(log_path))
    return args


def make_client(ui, store):
    setLanguage("en")
    config = _defaults()
    conn = store.data["connection"]
    config["playerPath"] = mpv_path()
    config["host"] = str(conn.get("host") or "syncplay.pl")
    config["port"] = int(conn.get("port") or constants.DEFAULT_PORT)
    config["name"] = str(conn.get("name") or "yucha")
    config["room"] = str(conn.get("room") or config["name"])
    config["password"] = None
    config["playerArgs"] = player_args(store_runtime_placeholder())
    client = SyncplayClient(MpvPlayer, ui, config)
    _keep_window_on_login_failure(client)
    return client


def store_runtime_placeholder():
    # Replaced by app.main once the bridge directory exists. player_args()
    # is called again with the real directory before mpv starts.
    return ""


def launch_player(client, runtime):
    client._config["playerArgs"] = player_args(runtime)
    MpvPlayer.run(
        client,
        client._config["playerPath"],
        "",
        client._config["playerArgs"],
    )
    # Network start must not spawn a second mpv.
    client._playerClass = None


def apply_login(client, host, port, name, room, password):
    name = (name or "").strip() or client.getUsername()
    room = (room or "").strip() or name
    client.setUsername(name)
    client.setRoom(room)
    client.defaultRoom = room
    client._config["host"] = host
    client._config["port"] = int(port)
    client._config["name"] = name
    client._config["room"] = room
    if password:
        client._serverPassword = hashlib.md5(password.encode("utf-8")).hexdigest()
    else:
        client._serverPassword = None


def submit_login(client, host, port, name, room, password):
    """Apply the form. Reconnect only when the login itself changed.

    A room change on the same server is a room update. A new host, port,
    username, or password has to open a new connection. mpv stays up either way.
    """
    port = int(port)
    name = (name or "").strip()
    room = (room or "").strip() or name
    new_hash = hashlib.md5(password.encode("utf-8")).hexdigest() if password else None
    same_login = (
        client._running
        and client._config.get("host") == host
        and int(client._config.get("port") or 0) == port
        and client.getUsername() == name
        and client._serverPassword == new_hash
    )
    apply_login(client, host, port, name, room, password)
    if same_login:
        client.setRoom(room)
        client.sendRoom()
        return
    if client._running:
        client.stop(True)
    connect_network(client, host, port)


def connect_network(client, host, port):
    if client._running:
        client.setRoom(client._config["room"])
        client.sendRoom()
        return
    client._running = True
    client.protocolFactory = SyncClientFactory(client)
    if "[" in host:
        host = host.strip("[]")
    port = int(port)
    client._endpoint = HostnameEndpoint(reactor, host, port)
    try:
        import pem
        from twisted.internet.ssl import Certificate, optionsForClientTLS, trustRootFromCertificates
        certs = pem.parse_file(SSL_CERT_FILE)
        trust = trustRootFromCertificates([Certificate.loadPEM(str(cert)) for cert in certs])
        client.protocolFactory.options = optionsForClientTLS(hostname=host, trustRoot=trust)
        client._clientSupportsTLS = True
    except Exception as exc:
        client.ui.showDebugMessage(str(exc))
        client.protocolFactory.options = None
        client._clientSupportsTLS = False

    def retry(retries):
        client._performRetryStateReset()
        if retries == 0:
            client.onDisconnect()
        if retries > constants.RECONNECT_RETRIES:
            reactor.callLater(
                0.1, client.ui.showErrorMessage,
                getMessage("connection-failed-notification"), True)
            reactor.callLater(0.1, client.stop, True)
            return None
        return 0.1 * (2 ** min(retries, 5))

    client._reconnectingService = ClientService(
        client._endpoint, client.protocolFactory, retryPolicy=retry)
    try:
        wait = client._reconnectingService.whenConnected(failAfterFailures=1)
    except TypeError:
        wait = client._reconnectingService.whenConnected()
    client._reconnectingService.startService()

    def connected_now(protocol):
        try:
            host_ip = protocol.transport.addr[0]
        except Exception:
            host_ip = host
        client.ui.showMessage(
            getMessage("reachout-successful-notification").format(host, host_ip))

    def failed(_result):
        reactor.callLater(
            0.1, client.ui.showErrorMessage,
            getMessage("connection-failed-notification"), True)
        reactor.callLater(0.1, client.stop, True)

    wait.addCallbacks(connected_now, failed)
    client.ui.showMessage(getMessage("connection-attempt-notification").format(host, port))


def _keep_window_on_login_failure(client):
    original = client.stop

    def stop(prompt=False):
        # prompt=True is Syncplay's "connection failed" path. Keep mpv open.
        if prompt:
            client._running = False
            service = getattr(client, "_reconnectingService", None)
            if service is not None:
                try:
                    service.stopService()
                except Exception:
                    pass
            client.destroyProtocol()
            return
        original(False)

    client.stop = stop
