from __future__ import annotations

import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QDesktopServices

from .. import localmodels, qq
from ..desktop.session import Session
from ..desktop.text import t
from ..i18n import detect_locale, get_locale, set_locale, LOCALE_LABELS
from ..onboarding import create_fish, default_pack_parent, load_config, remember_pack, save_config
from ..settings import PRESETS, desktop_executable, load_settings, load_ui_settings, save_ui_settings, set_autostart, test_brain, ui_settings_path
from ..util import read_json, write_json_atomic
from .models import Rows
from .avatar_view import normalized_view
from .avatar_expression import mood_style, choose_expression
from ..live2d_model import DEFAULT_MODEL, MODEL_CREDIT, descriptor
from ..plugins import PluginManager


class Bridge(QObject):
    stateChanged = Signal()
    preferencesChanged = Signal()
    formChanged = Signal()
    codexUsageChanged = Signal()
    workbuddyUsageChanged = Signal()
    localeChanged = Signal()
    diaryChanged = Signal()
    memoryChanged = Signal()
    memorySaved = Signal(str)
    continuityChanged = Signal()
    semanticChanged = Signal()
    factsChanged = Signal()
    factSaved = Signal()
    factDateLoaded = Signal()
    factDateSaved = Signal()
    learningChanged = Signal()
    learningSaved = Signal()
    reminderSaved = Signal()
    relationshipsChanged = Signal()
    relationshipSaved = Signal()
    disclosureChanged = Signal()
    disclosureSaved = Signal()
    lifeStoryChanged = Signal()
    lifeStorySaved = Signal()
    mediaChanged = Signal()
    mediaSaved = Signal()
    archiveChanged = Signal()
    archiveProgressed = Signal(str, object)
    archiveRequested = Signal()
    chatUpdated = Signal(bool)
    operationFinished = Signal(str, bool)
    closeReady = Signal()
    completed = Signal(int, object, object)
    petAction = Signal(str)
    avatarUtterance = Signal("QVariantMap")
    avatarReloadRequested = Signal()
    pluginsChanged = Signal()

    def __init__(self, pack=None, brain_override="", *, timers=True, acquire_lock=None):
        super().__init__()
        self.session = None
        self.pack = Path(pack) if pack else None
        self.brain_override = brain_override
        self.acquire_lock = acquire_lock
        self.snapshot = {}
        self._ready = False
        self._busy = False
        self._avatar_thinking = False
        self._closing = False
        self._closed = False
        self._codex_usage = ""
        self._workbuddy_usage = ""
        self._notice = t("今天也一起慢慢来。")
        self._notice_revision = 0
        self._default_notice = True
        self._error = False
        self._draft = ""
        self._draft_request_id = ""
        self._draft_request_text = ""
        self._locale_revision = 0
        self._diary_text = ""
        self._diary_day = 0
        self._diary_revision = 0
        self._diary_status = "empty"
        self._diary_error = ""
        self._query = ""
        self._forgotten = False
        self._history = False
        self._memory_detail = {}
        self._continuity = {}
        self._semantic = {}
        self._facts = {}
        self._fact_time = {}
        self._fact_date = {}
        self._fact_date_request_payload = None
        self._fact_date_request_id = ""
        self._learning = {}
        self._learning_request_payload = None
        self._learning_request_id = ""
        self._reminder_request_data = None
        self._reminder_request_id = ""
        self._reminder_change_payload = None
        self._reminder_change_id = ""
        self._relationships = {}
        self._relationship_request_payload = None
        self._relationship_request_id = ""
        self._relationship_history = False
        self._disclosure = {}
        self._disclosure_request_payload = None
        self._disclosure_request_id = ""
        self._life_story = {}
        self._life_story_request_payload = None
        self._life_story_request_id = ""
        self._media = {}
        self._media_detail = {}
        self._media_request_payload = None
        self._media_request_id = ""
        self._incoming_media_payload = None
        self._incoming_media_request_id = ""
        self._archive_info = {}
        self._archive_result = {}
        self._archive_progress = {}
        self._archive_running = False
        self._archive_token = ""
        self._archive_cancel = None
        self._fact_request_payload = None
        self._fact_request_id = ""
        self._fact_query = ""
        self._fact_audit = False
        self._fact_offset = 0
        self._memory_request_id = ""
        self._memory_request_payload = None
        self._life_section = "growth"
        self._form = {}
        self._api_key_draft = ""
        self._saved = {}
        self._qq_form = {"owner": "", "groups": [], "self_id": "", "onebot_http": qq.DEFAULT_ONEBOT_HTTP,
                         "port": qq.DEFAULT_QQ_PORT, **qq.config_defaults()}
        self._qq_saved = dict(self._qq_form)
        self._models = []
        from ..channels import defaults
        self._channel_form = defaults("telegram")
        self._channel_status = []
        self._qq_status = {}
        self._observation_history = {"pending": 0, "attempts": 0, "date": "", "batches": [], "page": 0, "pages": 1, "pending_messages": []}
        self._plugins = PluginManager()
        self._plugin_rows = []
        self._plugin_output = {}
        self._plugin_running = ""
        self._plugin_cancel = None
        self._preferences = read_json(ui_settings_path(), {})
        if not isinstance(self._preferences, dict):
            self._preferences = {}
        self._preferences.update(normalized_view(self._preferences))
        set_locale(os.environ.get("SEEDBANK_LANG") or load_config().get("language") or detect_locale())
        self._preferences["language"] = get_locale()
        self._preferences.update(load_ui_settings())
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="seedbank-quick")
        self._pending = {}
        self._sequence = 0
        self.completed.connect(self._complete, Qt.ConnectionType.QueuedConnection)
        self.archiveProgressed.connect(self._archive_update, Qt.ConnectionType.QueuedConnection)
        self.operationFinished.connect(self._archive_finished)
        self.chat = Rows(self)
        self.days = Rows(self)
        self.memories = Rows(self)
        self.life = Rows(self)
        self._pulse = QTimer(self)
        self._pulse.setInterval(60000)
        self._pulse.timeout.connect(self.pulse)
        self._watch = QTimer(self)
        self._watch.setInterval(2000)
        self._watch.timeout.connect(self.watch)
        self._timers = timers
        if self.pack:
            QTimer.singleShot(0, lambda: self.openPack(str(self.pack)))

    @Property(bool, notify=stateChanged)
    def ready(self):
        return self._ready

    @Property(bool, notify=stateChanged)
    def busy(self):
        return self._busy

    @Property(bool, notify=stateChanged)
    def avatarThinking(self):
        return self._avatar_thinking

    @Property(bool, notify=stateChanged)
    def closing(self):
        return self._closing

    @Property(str, notify=stateChanged)
    def notice(self):
        return t("今天也一起慢慢来。") if self._default_notice else self._notice

    @Property(bool, notify=stateChanged)
    def error(self):
        return self._error

    @Property(str, notify=stateChanged)
    def name(self):
        return self.session.name if self.session else "Seedbank"

    @Property(str, notify=stateChanged)
    def avatar(self):
        return str(self.snapshot.get("profile", {}).get("avatar") or "seed")

    @Property(int, notify=stateChanged)
    def day(self):
        return int(self.snapshot.get("day", 1))

    @Property(str, notify=stateChanged)
    def nextDate(self):
        from datetime import date, timedelta
        try:
            return (date.fromisoformat(self.snapshot.get("date", "")) + timedelta(days=1)).isoformat()
        except (ValueError, OverflowError):
            return ""

    @Property("QVariantList", notify=stateChanged)
    def pendingReminders(self):
        return [row for row in self.snapshot.get("pendingRequests", []) if row["payload"].get("kind") in ("reminder_edit", "reminder_change")]

    @Property("QVariantList", notify=stateChanged)
    def reminderRows(self):
        from ..reminder_changes import fingerprint
        rows = self.snapshot.get("states", {}).get("hands", {}).get("reminders", [])
        return [{**row, "expected": fingerprint(row), "label": row["id"] + " · " + row["text"] + " · " + t(row["status"])}
                for row in reversed(rows)]

    @Property(str, notify=stateChanged)
    def mood(self):
        return str(self.snapshot.get("states", {}).get("mood", {}).get("mood") or t("安静"))

    @Property(str, notify=stateChanged)
    def avatarMood(self):
        return mood_style(self.mood, self.energy)

    @Slot(str, result=str)
    def avatarExpression(self, previous):
        return choose_expression(self.avatarMood, previous)

    @Property(float, notify=stateChanged)
    def energy(self):
        try:
            return max(0, min(1, float(self.snapshot.get("states", {}).get("mood", {}).get("energy", 1))))
        except (TypeError, ValueError):
            return 1

    @Property("QVariantMap", notify=preferencesChanged)
    def preferences(self):
        return self._preferences

    @Property(str, notify=preferencesChanged)
    def avatarModel(self):
        return str(self._preferences.get("live2d_model") or DEFAULT_MODEL)

    @Property(str, constant=True)
    def avatarCredit(self):
        return MODEL_CREDIT

    @Property("QVariantList", notify=pluginsChanged)
    def plugins(self):
        return self._plugin_rows

    @Property("QVariantMap", notify=pluginsChanged)
    def pluginOutput(self):
        return self._plugin_output

    @Property(str, notify=pluginsChanged)
    def runningPlugin(self):
        return self._plugin_running

    def _set_plugins(self, rows):
        self._plugin_rows = rows
        self.pluginsChanged.emit()

    @Slot()
    def refreshPlugins(self):
        if not self._busy:
            self.submit("plugins-refresh", self._plugins.list, self._set_plugins)

    def _plugin_change(self, action, message):
        if self._busy:
            return
        def work():
            action()
            return self._plugins.list()
        def done(rows):
            self._set_plugins(rows)
            self.notify(t(message))
        self.submit("plugins-change", work, done)

    @Slot(str)
    def addPlugin(self, value):
        url = QUrl(value)
        if not url.isLocalFile():
            self.notify(t("请选择本地 plugin.json 文件。"), True)
            return
        manifest = Path(url.toLocalFile())
        if manifest.name != "plugin.json":
            self.notify(t("请选择本地 plugin.json 文件。"), True)
            return
        self._plugin_change(lambda: self._plugins.install(manifest.parent), "插件已添加；确认来源后才能启用。")

    @Slot()
    def addExamplePlugin(self):
        base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[4]
        self._plugin_change(lambda: self._plugins.install(base / "examples/plugins/hello"), "插件已添加；确认来源后才能启用。")

    @Slot(str, bool)
    def enablePlugin(self, identifier, enabled):
        self._plugin_change(lambda: self._plugins.enable(identifier, enabled), "插件状态已保存。")

    @Slot(str, "QVariantMap")
    def configurePlugin(self, identifier, values):
        self._plugin_change(lambda: self._plugins.configure(identifier, dict(values)), "插件配置已保存。")

    @Slot(str)
    def removePlugin(self, identifier):
        self._plugin_change(lambda: self._plugins.remove(identifier), "插件已从列表移除，文件保留。")

    @Slot(str)
    def openPluginFolder(self, identifier):
        # Resolve a registered managed folder; no arbitrary URL from a manifest.
        try:
            row = self._plugins._read().get(identifier)
            if row:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._plugins._folder(row))))
        except (OSError, ValueError) as error:
            self.notify(str(error), True)

    @Slot()
    def pluginDeveloperGuide(self):
        QDesktopServices.openUrl(QUrl("https://github.com/AmatsukiRen/seedbank-public/blob/main/docs/plugins.md"))

    @Slot(str, str, "QVariantMap")
    def runPlugin(self, identifier, text, values):
        if not self._ready or not self.lifeActive or self._busy or self._closing or self._closed:
            return
        cancel = Event()
        self._plugin_cancel = cancel
        self._plugin_running = identifier
        self._plugin_output = {}
        self.pluginsChanged.emit()
        config = dict(values)
        def work():
            if cancel.is_set():
                raise ValueError(t("插件运行已停止。"))
            self._plugins.configure(identifier, config)
            output = self._plugins.run(identifier, text, cancel=cancel)
            return output, self._plugins.list()
        def finish(result, error=False):
            self._plugin_running = ""
            self._plugin_cancel = None
            if not error:
                result, self._plugin_rows = result
            self._plugin_output = {"id": identifier, "text": t(result) if error else result, "error": error}
            self.pluginsChanged.emit()
        if not self.submit("plugins-run", work, finish, on_error=lambda message: finish(message, True)):
            finish("插件运行未开始。", True)

    @Slot()
    def stopPlugin(self):
        if self._plugin_cancel is not None:
            self._plugin_cancel.set()
        self._plugins.cancel()

    @Slot(str)
    def selectAvatarModel(self, value):
        url = QUrl(value)
        if not url.isLocalFile():
            self.notify(t("请选择本地 Live2D 模型文件。"), True)
            return
        try:
            path = str(Path(url.toLocalFile()).expanduser().resolve())
            descriptor(path)
        except (OSError, ValueError, TypeError) as error:
            self.notify(str(error), True)
            return
        self.preference("live2d_model", path)
        if self.avatarModel == path:
            self.avatarReloadRequested.emit()

    @Slot()
    def reloadAvatar(self):
        self.avatarReloadRequested.emit()

    @Property("QVariantMap", notify=formChanged)
    def form(self):
        return self._form

    @Property("QVariantMap", notify=formChanged)
    def qqForm(self):
        return {**self._qq_form, "groups": ",".join(qq.parse_groups(self._qq_form.get("groups")))}

    @Property("QVariantMap", notify=formChanged)
    def channelForm(self):
        return self._channel_form

    @Property("QVariantList", notify=stateChanged)
    def channelStatus(self):
        return self._channel_status

    @Property("QVariantMap", notify=stateChanged)
    def observationHistory(self):
        return self._observation_history

    @Slot()
    def loadObservations(self):
        self._load_observations()

    @Slot(int)
    def observationPage(self, page):
        self._load_observations(page)

    def _load_observations(self, page=None, notice=None):
        if not self.session:
            return
        from ..observing import history
        page = self._observation_history.get("page", 0) if page is None else page
        def done(value):
            self._observation_history = value
            self.stateChanged.emit()
            if notice:
                self.notify(t(notice))
        self.submit("observation-history", lambda: history(self.pack, page), done)

    @Slot()
    def processObservations(self):
        if self.session:
            def done(value):
                notice = {"completed": "旁听整理已完成。", "failed": "旁听整理失败；本次额度已计入，不会自动重试。",
                    "daily_limit": "今日旁听整理额度已用完。", "inactive": "请先启动已配置旁听群的连接。"}.get(value["state"], "暂无到期的旁听内容。")
                self._load_observations(0, notice)
            self.submit("observation-process", lambda: self.session.process_observations(force=True), done)

    @Slot(str)
    def withdrawObservation(self, identifier):
        if self.session:
            self.submit("observation-withdraw", lambda: self.session.withdraw_observation(identifier), lambda value: self.loadObservations())

    @Slot(result="QVariantList")
    def channelPresets(self):
        from ..channels import PRESETS as channels
        return [{**row, "label": t(row["label"]), "hint": t(row["hint"])} for row in channels]

    @Slot(str)
    def selectChannel(self, kind):
        from ..channels import load_config, defaults
        self._channel_form = load_config(self.pack, kind) if self.pack else defaults(kind)
        self.formChanged.emit()

    @Slot(str, str)
    def editChannel(self, key, value):
        if key in self._channel_form and key != "id":
            self._channel_form[key] = value
            self.formChanged.emit()

    @Slot()
    def saveChannel(self):
        if not self.session:
            return
        from ..channels import save_config
        try:
            self._channel_form = save_config(self.pack, self._channel_form)
            self.formChanged.emit()
            self.notify(t("渠道配置已保存；不会自动连接。"))
        except (ValueError, OSError) as error:
            self.notify(str(error), True)

    @Slot(bool)
    def toggleChannel(self, start):
        if not self.session:
            return
        config = dict(self._channel_form)
        def work():
            if start:
                self.session.channels.start(config)
            else:
                self.session.channels.stop(config["id"])
            return self.session.channels.summaries()
        def done(result):
            self._channel_status = result
            self.stateChanged.emit()
            self.notify(t("连接进程已启动") if start else t("已停止连接"))
        self.submit("channel", work, done)

    @Property("QVariantList", notify=formChanged)
    def localModels(self):
        return self._models

    @Property(bool, notify=stateChanged)
    def qqRunning(self):
        return bool(self.session and self.session.server)

    @Property(str, notify=stateChanged)
    def qqStatusText(self):
        server = self.session.server if self.session else None
        return qq.diagnostic_text(server.adapter.diagnostics()) if server else t("尚未启动")

    @Property(bool, notify=formChanged)
    def dirty(self):
        return self.conversationDirty or self._qq_form != self._qq_saved

    @Property(str, notify=diaryChanged)
    def diaryText(self):
        return self._diary_text

    @Property(int, notify=diaryChanged)
    def diaryDay(self):
        return self._diary_day

    @Property(str, notify=diaryChanged)
    def diaryStatus(self):
        return self._diary_status

    @Property(str, notify=diaryChanged)
    def diaryError(self):
        return self._diary_error

    @Property(str, notify=diaryChanged)
    def diaryDate(self):
        return next((str(row.get("date", "")) for row in self.days.rows if row["day"] == self._diary_day), "")

    @Property("QVariantMap", notify=memoryChanged)
    def memoryDetail(self):
        return self._memory_detail

    @Property("QVariantMap", notify=continuityChanged)
    def continuity(self):
        return self._continuity

    @Property("QVariantMap", notify=semanticChanged)
    def semantic(self):
        return self._semantic

    @Property("QVariantMap", notify=factsChanged)
    def facts(self):
        return self._facts

    @Property("QVariantMap", notify=factsChanged)
    def factTime(self):
        return self._fact_time

    @Property("QVariantMap", notify=factsChanged)
    def factDate(self):
        return self._fact_date

    @Property("QVariantMap", notify=learningChanged)
    def learning(self):
        return self._learning

    @Property("QVariantMap", notify=relationshipsChanged)
    def relationships(self):
        return self._relationships

    @Property("QVariantMap", notify=disclosureChanged)
    def disclosure(self):
        return self._disclosure

    @Property("QVariantMap", notify=lifeStoryChanged)
    def lifeStory(self):
        return self._life_story

    @Property("QVariantMap", notify=mediaChanged)
    def mediaArchive(self):
        return self._media

    @Property("QVariantMap", notify=mediaChanged)
    def mediaDetail(self):
        return self._media_detail

    @Property(bool, notify=mediaChanged)
    def mediaInputPending(self):
        return bool(self._incoming_media_request_id)

    @Property("QVariantMap", notify=archiveChanged)
    def archiveState(self):
        return {"info": self._archive_info, "result": self._archive_result, "progress": self._archive_progress,
                "running": self._archive_running, "cancelling": bool(self._archive_cancel and self._archive_cancel.is_set())}

    @Property(bool, notify=formChanged)
    def conversationDirty(self):
        return bool(self._api_key_draft) or self._form != self._saved

    @Property(str, notify=formChanged)
    def apiKeyDraft(self):
        return self._api_key_draft

    @Property(bool, constant=True)
    def localKeySupported(self):
        from ..credentials import supported
        return supported()

    @Property(bool, notify=formChanged)
    def remoteApi(self):
        from ..brain import is_local_endpoint
        return (self._form.get("adapter") in ("openai-compatible", "anthropic")
                and not is_local_endpoint(self._form.get("base_url")))

    @Property(str, notify=formChanged)
    def apiKeyStatus(self):
        from ..credentials import available
        if self._api_key_draft:
            return t("新 Key 尚未保存。保存后会清空输入框。")
        if available(self._form.get("api_key_ref")):
            return t("本机 API Key 已保存；留空保留，输入新 Key 后保存即可替换。")
        return t("本机没有此连接的 Key，请填写后保存。")

    @Slot(str)
    def editApiKey(self, value):
        self._api_key_draft = value
        self.formChanged.emit()

    @Property(str, notify=continuityChanged)
    def continuityText(self):
        from .continuity import describe
        return describe(self._continuity)

    @Property(int, notify=localeChanged)
    def localeRevision(self):
        return self._locale_revision

    @Property(str, notify=stateChanged)
    def draft(self):
        return self._draft

    @Property(str, constant=True)
    def defaultParent(self):
        return str(default_pack_parent())

    @Property("QVariantList", constant=True)
    def languages(self):
        return [{"code": code, "label": label} for code, label in LOCALE_LABELS.items()]

    @Slot(str, result=str)
    def translate(self, text):
        return t(text)

    @Slot(str, result=int)
    def textLength(self, text):
        # Match Python-side limits: Qt's Array.from(string) counts UTF-16
        # surrogate halves separately on supported Qt versions.
        return len(text)

    @Slot(result="QVariantList")
    def presets(self):
        return [{**preset, "label": t(preset["label"]), "hint": t(preset["hint"])} for preset in PRESETS]

    @Property(str, notify=formChanged)
    def providerHint(self):
        provider = self._form.get("provider")
        if provider:
            preset = next((row for row in PRESETS if row.get("provider") == provider), None)
            if preset:
                return t(preset["hint"])
        return t("选择平台后填写自己的 Key 和模型 ID。地址、地域与账户须匹配。")

    def notify(self, message, error=False):
        self._notice_revision += 1
        self._notice = str(message)
        self._default_notice = not error and self._notice == t("今天也一起慢慢来。")
        self._error = error
        self.stateChanged.emit()

    def submit(self, kind, work, callback, *, busy=True, on_error=None, thinking=False):
        if self._closed or self._closing or (busy and self._busy):
            return False
        if busy:
            self._busy = True
            # Local reads, saves and periodic pulses share busy, but must not
            # animate the model's loading symbol. Only explicit requests opt in.
            self._avatar_thinking = bool(thinking)
            self.notify(t("正在整理，请稍候…"))
        self._sequence += 1
        token = self._sequence
        self._pending[token] = kind, callback, busy, self._notice_revision, on_error

        def execute():
            try:
                result, error = work(), None
            except Exception as failure:
                result, error = None, str(failure)
            self.completed.emit(token, result, error)

        self._executor.submit(execute)
        return True

    @Slot(int, object, object)
    def _complete(self, token, result, error):
        pending = self._pending.pop(token, None)
        if pending is None or self._closed:
            return
        kind, callback, busy, notice_revision, on_error = pending
        if busy:
            self._busy = False
            self._avatar_thinking = False
        try:
            if error:
                if on_error is not None:
                    on_error(error)
                else:
                    self.notify(t(error) if kind in ("memory-history", "memory-revise", "settings") or kind.startswith(("semantic-", "facts-", "learning-", "reminder-", "relationships-", "disclosure-", "life-story-", "archive-", "lifecycle-", "plugins-", "observation-")) else error, True)
            else:
                callback(result)
        except Exception as failure:
            error = str(failure)
            self.notify(error, True)
        if busy and not self._busy and error is None and self._notice_revision == notice_revision:
            self.notify(t("今天也一起慢慢来。"))
        self.stateChanged.emit()
        self.operationFinished.emit(kind, error is None)
        if self._closing and not self._pending and not self._closed:
            self._finish_close()

    @Slot(str)
    def openPack(self, path):
        if self._ready or self._busy:
            return
        target = Path(QUrl(path).toLocalFile() if path.startswith("file:") else path).expanduser().resolve()
        birth = read_json(target / "birth.json", {})
        if not isinstance(birth, dict) or not birth.get("name"):
            self.notify(t("这个文件夹里没有可读取的出生记录。"), True)
            return
        if self.acquire_lock and not self.acquire_lock(target):
            self.notify(t("她的房间已经开着了。"), True)
            return

        def work():
            session = Session(target, self.brain_override)
            try:
                return session, session.snapshot(), load_settings(target)
            except Exception:
                session.close()
                raise

        def opened(result):
            self.session, snapshot, self._form = result
            self.pack = target
            previous_qq_pack = self._qq_form.get("pack")
            if not previous_qq_pack or Path(previous_qq_pack).expanduser().resolve() != target:
                # QQ reply defaults may be shared, but observation requires a choice for this individual.
                self._qq_form.update(observe_groups="", observe_daily_limit=4)
                self._qq_saved = dict(self._qq_form)
            self._saved = deepcopy(self._form)
            self._ready = True
            remember_pack(target)
            saved = read_json(ui_settings_path(), {})
            saved = saved if isinstance(saved, dict) else {}
            saved["last_pack"] = str(target)
            write_json_atomic(ui_settings_path(), saved)
            self.apply_snapshot(snapshot)
            self.formChanged.emit()
            unfinished = [r for r in snapshot.get("pendingRequests", [])
                          if r["payload"].get("kind") == "chat" and r["payload"].get("speaker") in ("主人", "owner")]
            if unfinished and not self._draft:
                latest = unfinished[-1]
                self._draft = latest["payload"]["text"]
                self._draft_request_id = latest["id"]
                self._draft_request_text = self._draft.strip()
                self.notify(t("找回一条未完成的输入，已放回输入框。是否发送由你决定。"))
            elif snapshot.get("recoveredOperations"):
                self.notify(t("已恢复到上一次完整记录，未自动重发对话。"))
            else:
                self.notify(t("今天也一起慢慢来。"))
            if self._timers:
                self._pulse.start()
                self._watch.start()
                QTimer.singleShot(1200, self.pulse)

        self.submit("open", work, opened)

    @Property("QVariantMap", notify=stateChanged)
    def lifecycle(self):
        return self.snapshot.get("states", {}).get("lifecycle", {"state": "active", "revision": 0, "history": []})

    @Property(bool, notify=stateChanged)
    def lifeActive(self):
        return self.lifecycle.get("state") == "active"

    @Slot()
    def loadLifecycle(self):
        if self.session and not self._busy:
            self.submit("lifecycle-status", self.session.snapshot, self.apply_snapshot)

    @Slot(str, str, int)
    def changeLifecycle(self, action, note, expected):
        if not self.session or self._busy:
            return

        def work():
            with self.session.lock:
                self.session.call("lifecycle", action=action, note=note, expected=expected, confirmed=True)
                return self.session.snapshot()

        def done(snapshot):
            self.apply_snapshot(snapshot)
            self.notify(t("已休眠，档案完整保留。" if not self.lifeActive else "已明确恢复，继续从当前日期记录。"))

        self.submit("lifecycle-change", work, done)

    @Slot(str, str, int)
    def createPack(self, name, parent, preset):
        if not 0 <= preset < len(PRESETS):
            return
        folder = QUrl(parent).toLocalFile() if parent.startswith("file:") else parent
        from ..brain import is_local_endpoint
        config = dict(PRESETS[preset])
        if config["adapter"] in ("openai-compatible", "anthropic") and not is_local_endpoint(config.get("base_url")):
            config["api_key_source"] = "local" if self.localKeySupported else "env"
        self.submit("create", lambda: create_fish(name, folder, config), lambda path: self.openPack(str(path)))

    def apply_snapshot(self, snapshot):
        previous = self.snapshot
        self.snapshot = snapshot
        if not self.lifeActive:
            self.stopPlugin()
        transcript = snapshot.get("transcript", [])
        if any(snapshot.get(key) != previous.get(key) for key in ("transcript", "day", "senses", "news")):
            rows = [{"who": row["who"], "text": row["text"],
                     "incoming": row["who"] == "fish" or row["who"].startswith(self.name), "observation": False} for row in transcript]
            rows.extend({"who": t("感知与见闻"), "text": text, "incoming": True, "observation": True}
                        for text in (snapshot.get("senses", []) + snapshot.get("news", []))[-6:])
            self.chat.replace(rows)
            self.chatUpdated.emit(snapshot.get("day") != previous.get("day"))
        if snapshot.get("days") != previous.get("days"):
            self.days.replace(list(reversed(snapshot.get("days", []))))
        if snapshot.get("memories") != previous.get("memories"):
            self.filterMemories(self._query, self._forgotten, self._history)
        if snapshot.get("states") != previous.get("states") or snapshot.get("day") != previous.get("day"):
            self.lifeSection(self._life_section)
        if self.days.rows and (self._diary_day == 0 or transcript != previous.get("transcript")
                              or snapshot.get("day") != previous.get("day")):
            self.selectDay(self._diary_day or self.day)
        self.stateChanged.emit()

    @Slot(str, bool)
    @Slot(str, bool, bool)
    def filterMemories(self, query, forgotten, history=False):
        self._query, self._forgotten, self._history = query, forgotten, history
        needle = query.strip().casefold()
        self.memories.replace([{**row, "forgotten": bool(row.get("forgotten"))}
                               for row in reversed(self.snapshot.get("memories", []))
                               if (forgotten or (not row.get("forgotten") and row.get("kind") != "forget"))
                               and (history or (not row.get("superseded") and row.get("recallable", True))
                                    or (forgotten and (row.get("forgotten") or row.get("kind") == "forget")))
                               and needle in str(row.get("text", "")).casefold()])

    @Slot(str, result=bool)
    def loadMemory(self, identifier):
        if not self.session or self._busy:
            return False
        self._memory_detail = {}
        self.memoryChanged.emit()

        def work():
            with self.session.lock:
                result = self.session.call("memories", action="history", memory_id=identifier)
                return result["history"], self.session.snapshot()

        def done(payload):
            self._memory_detail = payload[0]
            self.memoryChanged.emit()
            self.apply_snapshot(payload[1])

        return self.submit("memory-history", work, done)

    @Slot(str, str, str, str, str, result=bool)
    def saveMemoryRevision(self, identifier, text, reason, change_type, effective_on):
        if not self.session or self._busy:
            return False
        payload = {"kind": "memory_revision", "memory_id": identifier.strip(), "text": text.strip(),
                   "reason": reason.strip(), "change_type": change_type, "effective_on": effective_on.strip()}
        if payload != self._memory_request_payload:
            pending = next((row for row in self._memory_detail.get("pending", []) if row["payload"] == payload), None)
            self._memory_request_id = pending["id"] if pending else "memory_edit_" + uuid.uuid4().hex
            self._memory_request_payload = payload
        request_id = self._memory_request_id

        def work():
            with self.session.lock:
                result = self.session.call("memories", action="revise", memory_id=payload["memory_id"],
                                           text=payload["text"], reason=payload["reason"],
                                           change_type=payload["change_type"], effective_on=payload["effective_on"],
                                           request_id=request_id)
                detail = self.session.call("memories", action="history", memory_id=result["memory"]["id"])
                return result, detail["history"], self.session.snapshot()

        def done(result):
            self._memory_detail = result[1]
            self.memoryChanged.emit()
            self.apply_snapshot(result[2])
            self.memorySaved.emit(result[0]["memory"]["id"])
            self.notify(t("修订已保存，旧版本仍可查看。"))

        return self.submit("memory-revise", work, done)

    @Slot(str, bool, int, result=bool)
    def loadFacts(self, query, audit, offset):
        if not self.session or self._busy:
            return False
        self._fact_query, self._fact_audit, self._fact_offset = query, audit, max(0, offset)

        def done(response):
            self._facts = response["facts"]
            self.factsChanged.emit()

        return self.submit("facts-list", lambda: self.session.call("facts", action="list", query=query,
                           audit=audit, offset=max(0, offset), limit=30), done)

    @Slot(str, str, int, str, int, result=bool)
    def loadFactTime(self, query, on, offset, slot, record_offset):
        if not self.session or self._busy:
            return False
        self._fact_time = {}
        self.factsChanged.emit()

        def done(response):
            self._fact_time = response["fact_time"]
            self.factsChanged.emit()

        return self.submit("facts-time", lambda: self.session.call("facts", action="timeline", query=query,
                           on=on, offset=max(0, offset), limit=30, slot=slot,
                           record_offset=max(0, record_offset)), done)

    @Slot(str, "QVariantMap", result=bool)
    def editFact(self, action, data):
        if not self.session or self._busy:
            return False
        payload = {"kind": "fact_edit", "action": action, "data": dict(data)}
        if payload != self._fact_request_payload:
            pending = next((r for r in self._facts.get("pending", []) if r["payload"] == payload), None)
            self._fact_request_id = pending["id"] if pending else "fact_edit_" + uuid.uuid4().hex
            self._fact_request_payload = payload
        request_id = self._fact_request_id
        query, audit = self._fact_query, self._fact_audit

        def work():
            with self.session.lock:
                self.session.call("facts", action=action, data=payload["data"], request_id=request_id)
                result = self.session.call("facts", action="list", query=query, audit=audit, offset=0, limit=30)
                return result["facts"], self.session.snapshot()

        def done(result):
            self.apply_snapshot(result[1])
            self._facts = result[0]
            self._fact_time = {}
            self._fact_date = {}
            self._fact_offset = 0
            self.factsChanged.emit()
            self._fact_request_payload = None
            self._fact_request_id = ""
            self.factSaved.emit()
            self.notify(t("单项记录已保存，原始经历仍保留。"))

        return self.submit("facts-edit", work, done)

    @Slot(str, result=bool)
    def loadFactDate(self, target):
        if not self.session or self._busy:
            return False
        self._fact_date = {}
        self.factsChanged.emit()

        def done(response):
            self._fact_date = response["fact_date"]
            self.factsChanged.emit()
            self.factDateLoaded.emit()

        return self.submit("facts-date-detail", lambda: self.session.call("facts", action="date_detail", target=target), done)

    @Slot("QVariantMap", result=bool)
    def saveFactDate(self, data):
        if not self.session or self._busy:
            return False
        payload = {"kind": "fact_time_edit", "data": dict(data)}
        if payload != self._fact_date_request_payload:
            pending = next((r for r in self._fact_date.get("pending", []) if r["payload"] == payload), None)
            self._fact_date_request_id = pending["id"] if pending else "fact_time_" + uuid.uuid4().hex
            self._fact_date_request_payload = payload
        identifier = self._fact_date_request_id
        view = dict(self._fact_time)
        query, audit = self._fact_query, self._fact_audit

        def work():
            with self.session.lock:
                self.session.call("facts", action="date", data=payload["data"], request_id=identifier)
                detail = self.session.call("facts", action="date_detail", target=payload["data"]["target"])["fact_date"]
                timeline = self.session.call("facts", action="timeline", query=view.get("query", ""), on=view.get("on", ""),
                                             slot=view.get("slot", ""), limit=30, offset=0)["fact_time"]
                facts = self.session.call("facts", action="list", query=query, audit=audit, limit=30, offset=0)["facts"]
                return detail, timeline, facts, self.session.snapshot()

        def done(result):
            self.apply_snapshot(result[3])
            self._fact_date, self._fact_time, self._facts = result[:3]
            self._fact_offset = 0
            self._fact_date_request_payload = None
            self._fact_date_request_id = ""
            self.factsChanged.emit()
            self.factDateSaved.emit()
            self.notify(t("日期修订已保存，原记录和修改历史仍保留。"))

        return self.submit("facts-date-edit", work, done)

    @Slot(str, int, bool, result=bool)
    def loadRelationships(self, person_id, offset, history):
        if not self.session or self._busy:
            return False
        self._relationship_history = history

        def done(response):
            self._relationships = response["relationships"]
            self.relationshipsChanged.emit()

        return self.submit("relationships-list", lambda: self.session.call("relationships", action="list",
                           person_id=person_id, offset=max(0, offset), limit=30, history=history), done)

    @Slot(str, "QVariantMap", result=bool)
    def saveRelationship(self, action, data):
        return self._save_relationship(action, dict(data))

    @Slot(str, result=bool)
    def resumeRelationship(self, identifier):
        pending = next((r for r in self._relationships.get("pending", []) if r["id"] == identifier), None)
        return self._save_relationship(pending["payload"]["action"], pending["payload"]["data"], identifier) if pending else False

    def _save_relationship(self, action, data, identifier=""):
        if not self.session or self._busy:
            return False
        payload = {"kind": "relationship_edit", "action": action, "data": data}
        if identifier or payload != self._relationship_request_payload:
            pending = next((r for r in self._relationships.get("pending", []) if r["payload"] == payload), None)
            self._relationship_request_id = identifier or (pending["id"] if pending else "relationship_" + uuid.uuid4().hex)
            self._relationship_request_payload = payload
        request_id, history = self._relationship_request_id, self._relationship_history

        def work():
            with self.session.lock:
                result = self.session.call("relationships", action=action, data=data, request_id=request_id)
                selected = result.get("person_id") or data.get("person_id") or "owner"
                listing = self.session.call("relationships", action="list", person_id=selected, offset=0, limit=30, history=history)
                return listing["relationships"], self.session.snapshot()

        def done(result):
            self._relationships = result[0]
            self.relationshipsChanged.emit()
            self.apply_snapshot(result[1])
            self._relationship_request_payload = None
            self._relationship_request_id = ""
            self.relationshipSaved.emit()
            self.notify(t("相处记录已保存，原有版本仍保留。"))

        return self.submit("relationships-save", work, done)

    @Slot(str, int, int, bool, result=bool)
    def loadDisclosure(self, query, offset, record_offset, history):
        if not self.session or self._busy:
            return False

        def done(response):
            self._disclosure = response["disclosure"]
            self.disclosureChanged.emit()

        return self.submit("disclosure-list", lambda: self.session.call("disclosure", action="list", query=query,
                           offset=max(0, offset), record_offset=max(0, record_offset), limit=30, history=history), done)

    @Slot(str, result=bool)
    def resumeDisclosure(self, identifier):
        pending = next((r for r in self._disclosure.get("pending", []) if r["id"] == identifier), None)
        return self.saveDisclosure(pending["payload"]["action"], pending["payload"]["data"]) if pending else False

    @Slot(str, "QVariantMap", result=bool)
    def saveDisclosure(self, action, data):
        if not self.session or self._busy:
            return False
        data = deepcopy(dict(data))
        payload = {"kind": "disclosure_edit", "action": action, "data": data}
        if payload != self._disclosure_request_payload or not self._disclosure_request_id:
            pending = next((r for r in self._disclosure.get("pending", []) if r["payload"] == payload), None)
            self._disclosure_request_id = pending["id"] if pending else "disclosure_" + uuid.uuid4().hex
            self._disclosure_request_payload = payload
        request_id = self._disclosure_request_id
        query, history = self._disclosure.get("query", ""), self._disclosure.get("history", False)

        def work():
            with self.session.lock:
                self.session.call("disclosure", action=action, data=data, request_id=request_id)
                listing = self.session.call("disclosure", action="list", query=query, history=history)
                return listing["disclosure"], self.session.snapshot()

        def done(result):
            self._disclosure = result[0]
            self.disclosureChanged.emit()
            self.apply_snapshot(result[1])
            self._disclosure_request_payload = None
            self._disclosure_request_id = ""
            self.disclosureSaved.emit()
            self.notify(t("分享范围已保存。保存不会发送消息。"))

        return self.submit("disclosure-save", work, done)

    @Slot(str, int, int, bool, result=bool)
    def loadLifeStory(self, query, offset, source_offset, history):
        if not self.session or self._busy:
            return False

        def done(response):
            self._life_story = response["life_story"]
            self.lifeStoryChanged.emit()

        return self.submit("life-story-list", lambda: self.session.call("life_story", action="list", query=query,
                           offset=max(0, offset), source_offset=max(0, source_offset), limit=30, history=history), done)

    @Slot(str, int, result=bool)
    def loadMedia(self, query, offset):
        if not self.session or self._busy:
            return False

        def done(result):
            self._media = result["media"]
            self.mediaChanged.emit()

        return self.submit("media-list", lambda: self.session.call("media", action="list", query=query,
                           offset=max(0, offset), limit=30), done)

    @Slot(str, result=bool)
    def loadMediaDetail(self, identifier):
        if not self.session or self._busy:
            return False
        self._media_detail = {}
        self.mediaChanged.emit()

        def done(result):
            self._media_detail = result["media_detail"]
            self.mediaChanged.emit()

        return self.submit("media-detail", lambda: self.session.call("media", action="detail", asset_id=identifier), done)

    @Slot(str, result=bool)
    def resumeMedia(self, identifier):
        pending = next((r for r in self._media.get("pending", []) if r["id"] == identifier), None)
        if pending and pending["payload"].get("kind") == "media_intake":
            return self.processMediaInput(identifier, False)
        return self.saveMedia(pending["payload"]["action"], pending["payload"]["data"]) if pending else False

    @Slot(str, bool, result=bool)
    def processMediaInput(self, identifier, cancel):
        if not self.session or self._busy:
            return False
        query, offset = self._media.get("query", ""), self._media.get("offset", 0)
        selected = self._media_detail.get("id", "")

        def work():
            with self.session.lock:
                result = self.session.call("media", action="cancel_intake" if cancel else "resume_intake", request_id=identifier)
                listing = self.session.call("media", action="list", query=query, offset=offset)
                detail = self.session.call("media", action="detail", asset_id=selected)["media_detail"] if selected else {}
                return result, listing["media"], detail, self.session.snapshot()

        def done(result):
            self._media, self._media_detail = result[1], result[2]
            self.apply_snapshot(result[3])
            if self._incoming_media_request_id == identifier:
                self._incoming_media_payload, self._incoming_media_request_id = None, ""
            self.mediaChanged.emit()
            self.notify(t("原件保留，后续处理已停止。") if result[0].get("cancelled") else t("已从保存的原件继续处理。"))

        return self.submit("media-intake-action", work, done)

    @Slot(str, "QVariantMap", result=bool)
    def saveMedia(self, action, data):
        if not self.session or self._busy:
            return False
        data = {k: str(dict(data).get(k) or "").strip() for k in ("asset_id", "note", "reason")}
        payload = {"kind": "media_edit", "action": action, "data": data}
        if payload != self._media_request_payload or not self._media_request_id:
            pending = next((r for r in self._media.get("pending", []) if r["payload"] == payload), None)
            self._media_request_id = pending["id"] if pending else "media_" + uuid.uuid4().hex
            self._media_request_payload = payload
        request_id = self._media_request_id
        query, offset = self._media.get("query", ""), self._media.get("offset", 0)

        def work():
            with self.session.lock:
                result = self.session.call("media", action=action, data=data, request_id=request_id)
                detail = self.session.call("media", action="detail", asset_id=data["asset_id"])
                listing = self.session.call("media", action="list", query=query, offset=offset)
                return result, detail["media_detail"], listing["media"], self.session.snapshot()

        def done(result):
            self._media_detail, self._media = result[1], result[2]
            self.mediaChanged.emit()
            self.apply_snapshot(result[3])
            self._media_request_payload, self._media_request_id = None, ""
            self.mediaSaved.emit()
            vision = result[0].get("vision", {})
            if action == "revisit" and not vision.get("ok"):
                self.notify(t("原件已保留，本次没有获得新的视觉解释。") + " " + str(vision.get("reason") or ""))
            else:
                self.notify(t("材料记录已保存，旧解释仍可查看。"))

        return self.submit("media-save", work, done)

    @Slot(str, result=bool)
    def openMediaCopy(self, identifier):
        if not self.session or self._busy:
            return False

        def done(result):
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(result["file"]))
            self.notify(t("原件副本已导出：{file}", file=result["file"]) + ("" if opened else " " + t("请手动打开此文件。")))

        return self.submit("media-export", lambda: self.session.call("media", action="export", asset_id=identifier), done)

    @Slot(str, result=bool)
    def resumeLifeStory(self, identifier):
        pending = next((r for r in self._life_story.get("pending", []) if r["id"] == identifier), None)
        return self.saveLifeStory(pending["payload"]["action"], pending["payload"]["data"]) if pending else False

    @Slot(str, "QVariantMap", result=bool)
    def saveLifeStory(self, action, data):
        if not self.session or self._busy:
            return False
        data = deepcopy(dict(data))
        payload = {"kind": "life_story_edit", "action": action, "data": data}
        if payload != self._life_story_request_payload or not self._life_story_request_id:
            pending = next((r for r in self._life_story.get("pending", []) if r["payload"] == payload), None)
            self._life_story_request_id = pending["id"] if pending else "life_story_" + uuid.uuid4().hex
            self._life_story_request_payload = payload
        request_id = self._life_story_request_id
        query, history = self._life_story.get("query", ""), self._life_story.get("history", False)

        def work():
            with self.session.lock:
                self.session.call("life_story", action=action, data=data, request_id=request_id)
                listing = self.session.call("life_story", action="list", query=query, history=history)
                return listing["life_story"], self.session.snapshot()

        def done(result):
            self._life_story = result[0]
            self.lifeStoryChanged.emit()
            self.apply_snapshot(result[1])
            self._life_story_request_payload = None
            self._life_story_request_id = ""
            self.lifeStorySaved.emit()
            self.notify(t("人生回顾已保存，原始经历仍保留。"))

        return self.submit("life-story-save", work, done)

    @Slot(result=bool)
    def exportLifeStory(self):
        if not self.session or self._busy:
            return False
        return self.submit("life-story-export", lambda: self.session.call("life_story", action="export"),
                           lambda result: self.notify(t("私人回顾已导出：{file}", file=result["file"])))

    @Slot(str, int, result=bool)
    def loadLearning(self, goal_id, offset):
        if not self.session or self._busy:
            return False

        def done(response):
            self._learning = response["learning"]
            self.learningChanged.emit()

        return self.submit("learning-list", lambda: self.session.call("learning", action="list", goal_id=goal_id,
                           offset=max(0, offset), limit=30), done)

    @Slot(str, "QVariantMap", result=bool)
    def saveLearning(self, action, data):
        return self._save_learning(action, dict(data))

    @Slot(str, result=bool)
    def resumeLearning(self, identifier):
        pending = next((r for r in self._learning.get("pending", []) if r["id"] == identifier), None)
        if not pending:
            return False
        payload = pending["payload"]
        if payload["kind"] == "practice":
            return self._save_learning("practice", {k: v for k, v in payload.items() if k != "kind"}, identifier)
        return self._save_learning(payload["action"], payload["data"], identifier)

    def _save_learning(self, action, data, identifier=""):
        if not self.session or self._busy:
            return False
        payload = ({"kind": "practice", **data} if action == "practice" else
                   {"kind": "learning_edit", "action": action, "data": data})
        if identifier or payload != self._learning_request_payload:
            pending = next((r for r in self._learning.get("pending", []) if r["payload"] == payload), None)
            self._learning_request_id = identifier or (pending["id"] if pending else "learning_" + uuid.uuid4().hex)
            self._learning_request_payload = payload
        request_id = self._learning_request_id

        def work():
            with self.session.lock:
                result = self.session.call("learning", action=action, data=data, request_id=request_id)
                goal_id = result.get("goal_id") or data.get("goal_id") or ""
                listing = self.session.call("learning", action="list", goal_id=goal_id, offset=0, limit=30)
                return listing["learning"], self.session.snapshot(), result.get("succeeded") is False

        def done(result):
            self.apply_snapshot(result[1])
            self._learning = result[0]
            self.learningChanged.emit()
            self._learning_request_payload = None
            self._learning_request_id = ""
            self.learningSaved.emit()
            self.notify(t("本次未生成作品，尝试已记录。再次发起会作为新的尝试。") if result[2]
                        else t("练习记录已保存，下一次尝试可参考这些反馈。"))

        return self.submit("learning-save", work, done)

    @Slot(int, result=bool)
    def selectDay(self, day):
        if not self.session or self._closing or self._closed or day not in [row["day"] for row in self.days.rows]:
            return False
        if day == self._diary_day and self._diary_status == "loading":
            return False
        if day != self._diary_day:
            self._diary_text = ""
        self._diary_day = day
        self._diary_revision += 1
        revision = self._diary_revision
        self._diary_status, self._diary_error = "loading", ""
        self.diaryChanged.emit()

        def loaded(text):
            if revision == self._diary_revision:
                self._diary_text = text
                self._diary_status = "ready" if text.strip() else "empty"
                self.diaryChanged.emit()

        def failed(error):
            if revision == self._diary_revision:
                self._diary_text = ""
                self._diary_status, self._diary_error = "error", t(error)
                self.diaryChanged.emit()

        return self.submit("diary", lambda: self.session.diary(day), loaded, busy=False, on_error=failed)

    def operate(self, operation, **fields):
        if not self.session:
            return False

        def work():
            with self.session.lock:
                result = self.session.call(operation, **fields)
                return result, self.session.snapshot()

        sent = self._draft

        def done(payload):
            if operation == "message" and self._draft == sent:
                self._draft = ""
                self._draft_request_id = ""
                self._draft_request_text = ""
            self.apply_snapshot(payload[1])
            if operation == "work" and payload[0].get("work", {}).get("succeeded") is False:
                self.notify(t("本次未生成作品，尝试已记录。再次发起会作为新的尝试。"))
                return
            if operation == "message":
                if not payload[0].get("replayed") and payload[0].get("reply"):
                    from ..presentation import utterance
                    self.avatarUtterance.emit(utterance(payload[0]["reply"], payload[0].get("presentation")))
            else:
                self.petAction.emit("mood")
            self.notify(t("已经记下来了。"))

        return self.submit(operation, work, done, thinking=operation in ("message", "work", "day"))

    @Slot(str)
    def setDraft(self, text):
        self._draft = text

    @Slot()
    def send(self):
        message = self._draft.strip()
        if not message or len(message) > 2000:
            self.notify(t("先写一点想说的话吧。") if not message else t("一条消息最多 2000 字"), True)
            return
        if not self._draft_request_id or message != self._draft_request_text:
            self._draft_request_id = "desktop_" + uuid.uuid4().hex
            self._draft_request_text = message
        if self.operate("message", text=message, request_id=self._draft_request_id):
            self.petAction.emit("think")

    @Slot(str)
    def sendPhoto(self, url):
        self._send_media("image", url, t("给你看样东西"))

    @Slot(str)
    def sendSound(self, url):
        self._send_media("sound", url, t("给你听一段声音"))

    def _send_media(self, operation, url, note):
        if not self.session or self._busy:
            return False
        payload = {"operation": operation, "path": QUrl(url).toLocalFile(), "note": note}
        # Selecting a file is a new delivery, even at the same path. The explicit
        # Continue button retries the previous archived input instead.
        self._incoming_media_payload = payload
        self._incoming_media_request_id = "desktop_media_" + uuid.uuid4().hex
        self.mediaChanged.emit()
        return self.retryMediaInput()

    @Slot(result=bool)
    def retryMediaInput(self):
        if not self.session or self._busy or not self._incoming_media_payload or not self._incoming_media_request_id:
            return False
        payload = dict(self._incoming_media_payload)
        identifier = self._incoming_media_request_id
        expected = {"slots": [payload["operation"]], "note": payload["note"], "vision": None,
                    "person_id": "owner", "audience_id": "owner"}

        def work():
            with self.session.lock:
                previous = self.session.call("media", action="probe_intake", request_id=identifier, expected=expected)
                if previous.get("found"):
                    result = self.session.call("media", action="resume_intake", request_id=identifier) if previous.get("pending") else previous
                else:
                    result = self.session.call(payload["operation"], path=payload["path"], note=payload["note"], request_id=identifier)
                return result, self.session.snapshot()

        def done(result):
            self.apply_snapshot(result[1])
            if not result[0].get("pending"):
                self._incoming_media_payload, self._incoming_media_request_id = None, ""
            self.mediaChanged.emit()
            self.petAction.emit("mood")
            self.notify(t("原件已保存，可在记忆中查看处理状态。"))

        return self.submit("media-intake", work, done, thinking=True)

    @Slot(str)
    def forget(self, identifier):
        self.operate("memories", action="forget", memory_id=identifier)

    @Slot()
    def advanceDay(self):
        self.operate("day", days=1)

    @Slot(str)
    def compose(self, kind):
        if kind in ("poem", "letter", "drawing"):
            self.operate("work", action="compose", kind=kind)

    @Slot(str, int)
    def remind(self, text, day):
        if text.strip() and day >= self.day:
            self.operate("reminder", action="add", text=text.strip(), due_day=day)

    @Slot(str, str, result=bool)
    def remindOn(self, text, due_on):
        if not self.session or self._busy:
            return False
        data = {"text": text.strip(), "due_on": due_on.strip()}
        if data != self._reminder_request_data:
            pending = next((r for r in self.pendingReminders if r["payload"].get("kind") == "reminder_edit" and r["payload"]["data"] == data), None)
            self._reminder_request_id = pending["id"] if pending else "reminder_" + uuid.uuid4().hex
            self._reminder_request_data = data
        identifier = self._reminder_request_id

        def work():
            with self.session.lock:
                result = self.session.call("reminder", action="add", **data, request_id=identifier)
                return result, self.session.snapshot()

        def done(payload):
            self.apply_snapshot(payload[1])
            self._reminder_request_data = None
            self._reminder_request_id = ""
            self.reminderSaved.emit()
            self.notify(t("这条输入已取消，未建立提醒。" if payload[0].get("cancelled") else "已按日历日期记下提醒。"))

        return self.submit("reminder-save", work, done)

    @Slot(result=bool)
    def loadReminders(self):
        if not self.session or self._busy:
            return False
        return self.submit("reminder-load", self.session.snapshot, self.apply_snapshot)

    @Slot(str, "QVariantMap", result=bool)
    def changeReminder(self, action, data):
        if not self.session or self._busy:
            return False
        data = dict(data)
        data["reason"] = str(data.get("reason", "")).strip()
        if action == "revise":
            data["text"] = str(data.get("text", "")).strip()
            data["due_on"] = str(data.get("due_on", "")).strip()
        payload = {"kind": "reminder_change", "action": action, "data": data}
        if payload != self._reminder_change_payload:
            pending = next((r for r in self.pendingReminders if r["payload"] == payload), None)
            self._reminder_change_id = pending["id"] if pending else "reminder_change_" + uuid.uuid4().hex
            self._reminder_change_payload = deepcopy(payload)
        identifier = self._reminder_change_id

        def work():
            with self.session.lock:
                result = self.session.call("reminder", action=action, **data, request_id=identifier)
                return result, self.session.snapshot()

        def done(result):
            self.apply_snapshot(result[1])
            self._reminder_change_payload = None
            self._reminder_change_id = ""
            self.reminderSaved.emit()
            self.notify(t("已停止这条未完成操作。" if result[0].get("cancelled") else "提醒已更新，原内容与原因已保留。"))

        return self.submit("reminder-change", work, done)

    @Slot(str, result=bool)
    def cancelPendingReminder(self, identifier):
        if not self.session or self._busy:
            return False

        def work():
            with self.session.lock:
                self.session.call("reminder", action="cancel_pending", request_id=identifier)
                return self.session.snapshot()

        def done(snapshot):
            self.apply_snapshot(snapshot)
            if identifier == self._reminder_request_id:
                self._reminder_request_data = None
                self._reminder_request_id = ""
            if identifier == self._reminder_change_id:
                self._reminder_change_payload = None
                self._reminder_change_id = ""
            self.notify(t("已停止这条未完成操作。"))

        return self.submit("reminder-cancel", work, done)

    @Slot()
    def pulse(self):
        if self._ready and not self._busy:
            self.submit("pulse", self.session.pulse, lambda result: self.apply_snapshot(result["snapshot"]))

    @Slot()
    def watch(self):
        if self.session:
            server = self.session.server
            qq_status = server.adapter.diagnostics() if server else {}
            if qq_status != self._qq_status:
                self._qq_status = qq_status
                self.stateChanged.emit()
            states = self.session.channels.summaries()
            if states != self._channel_status:
                self._channel_status = states
                self.stateChanged.emit()
        if self.session and not self._busy and self.session.revision != self.snapshot.get("revision"):
            self.submit("refresh", self.session.snapshot, self.apply_snapshot)

    @Slot(str, "QVariant")
    def editSetting(self, key, value):
        if key == "api_key_source" and value == "local" and not self.localKeySupported:
            self.notify(t("此系统暂不支持本机密钥保存，请使用环境变量方式。"), True)
            self.formChanged.emit()
            return
        if key in ("adapter", "base_url", "api_key_source") and self._form.get(key) != value:
            self._api_key_draft = ""
            if key in ("adapter", "base_url"):
                self._form["api_key_ref"] = ""
            if key == "adapter":
                self._form["provider"] = ""
        self._form[key] = value
        self.formChanged.emit()

    @Slot(str, "QVariant")
    def editQQ(self, key, value):
        self._qq_form[key] = value
        self.formChanged.emit()

    @Slot(int)
    def applyPreset(self, index):
        if 0 <= index < len(PRESETS):
            self._form.update({key: PRESETS[index].get(key) or "" for key in ("adapter", "model", "base_url", "api_key_env")})
            from ..providers import COMPATIBILITY_DEFAULTS
            self._form.update({key: PRESETS[index].get(key, value) for key, value in COMPATIBILITY_DEFAULTS.items()})
            self._form["vision_model"] = ""
            self._api_key_draft = ""
            self._form["api_key_ref"] = ""
            self._form["api_key_source"] = "local" if self.localKeySupported and self.remoteApi else "env"
            self.formChanged.emit()

    @Property(str, notify=codexUsageChanged)
    def codexUsage(self):
        return self._codex_usage

    @Slot()
    def refreshCodexUsage(self):
        from ..codex_transport import usage_text
        self._codex_usage = usage_text()
        self.codexUsageChanged.emit()

    @Property(str, notify=workbuddyUsageChanged)
    def workbuddyUsage(self):
        return self._workbuddy_usage

    @Slot()
    def refreshWorkBuddyUsage(self):
        from ..workbuddy_transport import usage_text
        self._workbuddy_usage = usage_text()
        self.workbuddyUsageChanged.emit()

    def validated_form(self):
        patch = dict(self._form)
        for key, lower, upper, converter in (("temperature", 0, 2, float), ("daily_max", 1, 50, int)):
            try:
                patch[key] = converter(patch.get(key, .8 if key == "temperature" else 8))
                if not lower <= patch[key] <= upper:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError):
                raise ValueError(f"{key}: " + t("请输入 {lower} 到 {upper} 之间的数值。", lower=lower, upper=upper)) from None
        if patch.get("adapter") in ("codex", "workbuddy"):
            from ..settings import _clean_brain_patch
            key = patch["adapter"] + "_max_calls"
            patch.update(_clean_brain_patch({key: patch.get(key, 2)}))
        address = str(patch.get("base_url") or "").strip()
        if patch.get("adapter") not in ("codex", "workbuddy") and address and not address.startswith(("http://", "https://")):
            raise ValueError(t("接口地址需要以 http:// 或 https:// 开头。"))
        from ..providers import validate_connection
        validate_connection(patch)
        return patch

    @Slot()
    def saveSettings(self):
        try:
            patch = self.validated_form()
        except ValueError as error:
            self.notify(error, True)
            return
        submitted = dict(self._form)
        submitted_key = self._api_key_draft

        def saved(result):
            semantic_changed = any(key.startswith("semantic_") and self._saved.get(key) != value
                                   for key, value in result.items())
            self._saved = dict(result)
            if self._api_key_draft == submitted_key:
                self._api_key_draft = ""
            for key, value in result.items():
                if key == "api_key_ref" and any(self._form.get(field) != submitted.get(field)
                                                for field in ("adapter", "base_url")):
                    continue
                if self._form.get(key) == submitted.get(key):
                    self._form[key] = value
            self.formChanged.emit()
            self.notify(t("设置已保存。"))
            if semantic_changed:
                self._semantic = {}
                self.semanticChanged.emit()
                self.semanticIndex("status")

        if self.session:
            if submitted_key:
                self.submit("settings", lambda: self.session.save_brain(patch, api_key=submitted_key), saved)
            else:
                self.submit("settings", lambda: self.session.save_brain(patch), saved)

    @Slot()
    def testConnection(self):
        if self._api_key_draft:
            self.notify(t("请先保存 API Key，再测试连接。"), True)
            return
        try:
            patch = self.validated_form()
        except ValueError as error:
            self.notify(error, True)
            return
        self.submit("test", lambda: test_brain(self.pack, patch), lambda result: self.notify(result[1], not result[0]))

    @Slot(str, result=bool)
    def assessContinuity(self, action):
        if not self.session or action not in ("capture", "check", "status"):
            return False
        if action != "status" and self.conversationDirty:
            self.notify(t("请先保存对话设置，评估使用已保存的模型。"), True)
            return False

        def work():
            with self.session.lock:
                response = self.session.call("persona", action=action)
                if action == "status":
                    return response["persona"]
                return self.session.call("persona", action="status")["persona"]

        def done(result):
            self._continuity = result
            self.continuityChanged.emit()
            if action != "status":
                self.notify(t("评估记录已保存，请查看逐项结果。"))

        return self.submit("continuity-" + action, work, done)

    @Slot(str, result=bool)
    def semanticIndex(self, action):
        if not self.session or action not in ("status", "index", "clear"):
            return False
        if action != "status" and self.conversationDirty:
            self.notify(t("请先保存语义检索设置。"), True)
            return False

        def done(response):
            self._semantic = response["semantic"]
            self.semanticChanged.emit()
            if action == "index":
                self.notify(t("本批索引已保存，可继续补充剩余片段。"))
            elif action == "clear":
                self.notify(t("此模型的语义缓存已清空，原始经历仍保留。"))

        return self.submit("semantic-" + action, lambda: self.session.call("semantic", action=action), done)

    @Slot()
    def openContinuityFolder(self):
        if self.pack:
            folder = self.pack / "mind" / "continuity"
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder if folder.is_dir() else self.pack / "mind")))

    @Slot()
    def discover(self):
        def found(results):
            self._models = [{"label": source.get("label", ""), "model": model, "base_url": source["base_url"]}
                            for source in results for model in source.get("models", [])]
            self.formChanged.emit()
            self.notify(t("选择一个本地模型，然后保存。") if self._models else t("没有发现本地模型，请先启动本地模型服务。"))
        self.submit("discover", localmodels.discover, found)

    @Slot(int)
    def chooseModel(self, index):
        if 0 <= index < len(self._models):
            self._api_key_draft = ""
            self._form.update({"adapter": "openai-compatible", "model": self._models[index]["model"],
                               "base_url": self._models[index]["base_url"], "api_key_env": "",
                               "api_key_source": "env", "api_key_ref": "", "provider": "",
                               "response_format_mode": "prompt", "temperature_mode": "default", "vision_model": ""})
            self.formChanged.emit()

    def validated_qq(self):
        config = dict(self._qq_form)
        if not str(config.get("owner", "")).isdigit():
            raise ValueError(t("请输入有效的主人 QQ 号。"))
        try:
            config["port"] = int(config.get("port", ""))
            if not 1024 <= config["port"] <= 65535:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError(t("端口需要在 1024 到 65535 之间。")) from None
        if not str(config.get("onebot_http", "")).startswith(("http://", "https://")):
            raise ValueError(t("接口地址需要以 http:// 或 https:// 开头。"))
        config["groups"] = qq.parse_groups(config.get("groups"))
        config["secret_env"] = qq.secret_env(config)
        from ..observing import config as observation_config
        config.update(observation_config(config, "qq"))
        config["pack"] = str(self.pack)
        return config

    @Slot()
    def saveQQ(self):
        try:
            config = self.validated_qq()
        except ValueError as error:
            self.notify(error, True)
            return
        submitted = deepcopy(self._qq_form)

        def saved(result):
            self._qq_saved = {"owner": "", "groups": [], "self_id": "", "onebot_http": qq.DEFAULT_ONEBOT_HTTP,
                              "port": qq.DEFAULT_QQ_PORT, **result}
            for key, value in self._qq_saved.items():
                if self._qq_form.get(key) == submitted.get(key):
                    self._qq_form[key] = value
            self.formChanged.emit()
            self.notify(t("QQ 设置已保存；重新启动连接后生效。"))
        self.submit("qq-save", lambda: qq.save_config(config), saved)

    @Slot()
    def toggleQQ(self):
        if not self.session:
            return
        try:
            config = None if self.qqRunning else self.validated_qq()
        except ValueError as error:
            self.notify(error, True)
            return
        work = self.session.stop_qq if self.qqRunning else lambda: self.session.start_qq(config)
        self.submit("qq", work, lambda result: self.notify(t("QQ 连接已启动。") if result.get("running") else t("QQ 连接已停止。")))

    @Slot()
    def testQQ(self):
        address = str(self._qq_form.get("onebot_http") or "")
        self.submit("qq-test", lambda: qq.test_connection(address, os.environ.get("SEEDBANK_ONEBOT_TOKEN", "")),
                    lambda result: self.notify(str(result.get("nickname") or result.get("error") or result), not result.get("ok")))

    @Slot(float, float, float, result=bool)
    def setAvatarView(self, zoom, offset_x, offset_y):
        patch = normalized_view({"live2d_zoom": zoom, "live2d_offset_x": offset_x,
                                 "live2d_offset_y": offset_y})
        if all(self._preferences.get(key) == value for key, value in patch.items()):
            return True
        try:
            saved = read_json(ui_settings_path(), {})
            saved = saved if isinstance(saved, dict) else {}
            saved.update(patch)
            write_json_atomic(ui_settings_path(), saved)
            self._preferences.update(patch)
            self.preferencesChanged.emit()
            return True
        except (OSError, ValueError) as error:
            self.notify(error, True)
            self.preferencesChanged.emit()
            return False

    @Slot(str, "QVariant")
    def preference(self, key, value):
        allowed = ("desktop_theme", "desktop_large_text", "desktop_reduced_motion", "always_on_top", "autostart", "language", "live2d_model", "live2d_zoom")
        if key not in allowed:
            return
        try:
            if key == "desktop_theme" and value not in ("sky", "cream", "mint", "night"):
                return
            if key == "live2d_zoom":
                self.setAvatarView(float(value), self._preferences["live2d_offset_x"],
                                   self._preferences["live2d_offset_y"])
                return
            if key == "language":
                if value not in LOCALE_LABELS:
                    return
                save_config({"language": value})
                set_locale(value)
                self._locale_revision += 1
                self.localeChanged.emit()
                self.lifeSection(self._life_section)
                self.stateChanged.emit()
            elif key == "autostart":
                command = [desktop_executable()] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve().parents[2] / "seed.py"), "window", str(self.pack)]
                result = set_autostart(bool(value), command=command)
                if not result.get("ok"):
                    raise ValueError(result.get("message", ""))
            saved = read_json(ui_settings_path(), {})
            saved = saved if isinstance(saved, dict) else {}
            patch = {key: value}
            if key == "live2d_model" and value != self._preferences.get(key):
                patch.update(normalized_view({}))
            saved.update(patch)
            write_json_atomic(ui_settings_path(), saved)
            self._preferences.update(patch)
            self.preferencesChanged.emit()
        except (OSError, ValueError) as error:
            self.notify(error, True)
            self.preferencesChanged.emit()

    @Slot()
    def openFolder(self):
        if self.pack:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pack)))

    @Slot()
    def backupNow(self):
        if not self.session or self._busy:
            return
        from ..backup import create

        def work(progress, cancel):
            with self.session.lock:
                return create(self.pack, progress=progress, cancel=cancel)

        self.archiveRequested.emit()
        self._archive_task("create", work, lambda result: self.notify(t("备份已保存：{path}", path=result["file"])))

    @Slot()
    def showArchiveManager(self):
        self.archiveRequested.emit()

    @Slot(str, object)
    def _archive_update(self, token, progress):
        if self._archive_running and token == self._archive_token:
            self._archive_progress = dict(progress)
            self.archiveChanged.emit()

    @Slot(str, bool)
    def _archive_finished(self, kind, succeeded):
        if kind.startswith("archive-"):
            self._archive_running = False
            self.archiveChanged.emit()

    def _archive_task(self, action, work, done):
        from ..backup import BackupCancelled
        if self._busy or self._closing or self._closed:
            return False
        token = uuid.uuid4().hex
        cancel = Event()
        self._archive_token, self._archive_cancel = token, cancel
        self._archive_running, self._archive_progress, self._archive_result = True, {}, {}
        self.archiveChanged.emit()

        def run():
            try:
                return work(lambda state: self.archiveProgressed.emit(token, state), cancel)
            except BackupCancelled:
                return {"cancelled": True}

        def finished(result):
            if result.get("cancelled"):
                self.notify(t("已取消，未发布新的备份或恢复包。"))
            else:
                self._archive_result = dict(result) if action != "inspect" else {}
                done(result)
            self.archiveChanged.emit()

        accepted = self.submit("archive-" + action, run, finished)
        if not accepted:
            self._archive_running = False
            self.archiveChanged.emit()
        return accepted

    @Slot()
    def cancelArchive(self):
        if self._archive_running and self._archive_cancel:
            self._archive_cancel.set()
            self.archiveChanged.emit()

    @Slot()
    def clearBackupPreview(self):
        if not self._archive_running:
            self._archive_info = {}
            self.archiveChanged.emit()

    @staticmethod
    def _archive_path(value, resolve=True):
        path = Path(QUrl(value).toLocalFile() if value.startswith("file:") else value).expanduser()
        return path.resolve() if resolve else path.absolute()

    @Slot(str, result=bool)
    def inspectBackup(self, source):
        if self._busy or not source.strip():
            return False
        from ..backup import inspect_backup
        try:
            path = self._archive_path(source)
        except (OSError, ValueError, RuntimeError):
            self.notify(t("无法读取这个文件路径。"), True)
            return False
        self._archive_info = {}

        def done(result):
            self._archive_info = result
            self.notify(t("已读取备份清单，文件内容将在恢复时逐一核对。"))

        return self._archive_task("inspect", lambda progress, cancel: inspect_backup(path, progress=progress, cancel=cancel), done)

    @Slot(str, str, result=bool)
    def restoreBackup(self, source, destination):
        if self._busy or not source.strip() or not destination.strip():
            return False
        from ..backup import restore
        try:
            path, target = self._archive_path(source), self._archive_path(destination, resolve=False)
        except (OSError, ValueError, RuntimeError):
            self.notify(t("无法读取这个文件路径。"), True)
            return False
        if str(path) != self._archive_info.get("file"):
            self.notify(t("请先读取所选备份的信息。"), True)
            return False
        expected = self._archive_info["manifest_digest"]
        return self._archive_task("restore", lambda progress, cancel: restore(path, target, expected=expected, progress=progress, cancel=cancel),
                                  lambda result: self.notify(t("已恢复到新文件夹：{path}", path=result["pack"])))

    @Slot()
    def openBackups(self):
        if self.pack:
            folder = self.pack.parent / "SEEDbank-backups"
            if folder.is_dir():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @Slot(str)
    def lifeSection(self, section):
        if section not in ("growth", "heart", "works"):
            return
        self._life_section = section
        states = self.snapshot.get("states", {})
        agency, bonds, inner = (states.get(key, {}) for key in ("agency", "bonds", "inner"))
        memorial = states.get("memorial", {})
        rows = []

        def card(title, lines, action=""):
            rows.append({"title": t(title), "text": "\n\n".join(str(line) for line in lines if line), "action": action})

        if section == "growth":
            growth = states.get("development", {})
            from ..story_lineage import display_lines as interpretation_lines
            from ..goal_provenance import display_lines as provenance_lines
            card("长期目标", [g.get("title", "") + " · " + t(g.get("status", "active"))
                              + "\n" + t("下一步：{text}", text=g.get("next_step", ""))
                              + "\n" + t("理由：{text}", text=g.get("reason", ""))
                              + "\n" + "\n".join(provenance_lines(g))
                              + (("\n" + t("当前依据仍符合这次目标的完成条件。" if g.get("completion_current", {}).get("passed") else
                                            "历史上标记过完成，当前依据不足以确认；历史记录保留。")) if g.get("status") == "completed" else "")
                              + ("\n" + "\n".join(interpretation_lines(g)) if g.get("interpretation_updates") else "")
                              for g in growth.get("goals", [])]
                 or [t("目标会从经历和自己的选择中形成。")])
            card("正在形成的看法", [b.get("text", "") + "\n" + t("理由：{text}", text=b.get("reason", ""))
                                     + ("\n" + "\n".join(interpretation_lines(b)) if b.get("interpretation_updates") else "")
                                     for b in growth.get("beliefs", [])]
                 or [t("还没有留下有依据的新看法。")])
            from ..development import attempt_label
            from ..action_proposals import display_lines as proposal_lines
            card("行动与结果", [r.get("action", "") + " · " + t(r.get("status", "")) + " · " + attempt_label(r) + "\n" + r.get("detail", "")
                                  + "\n" + "\n".join(proposal_lines(r))
                                  for r in reversed(growth.get("outcomes", []))]
                 or [t("实际做过的事，会在这里留下结果。")])
            card("今天的小计划", [row.get("plan", "") for row in agency.get("plans", []) if row.get("day") == self.day]
                 or [t("今天还没有计划，先一起待一会儿。")], "day")
            from ..agency import history_line
            plan_changes = states.get("plan_history", {})
            card("今天的计划变化", [history_line(row) for row in plan_changes.get("records", [])]
                 + ([t("较早的计划变化仍保留在档案中。")] if plan_changes.get("has_more") else [])
                 or [t("今天还没有计划变化。")])
            from ..plan_links import display_lines as plan_review_lines
            card("计划与实际行动", plan_review_lines(growth.get("plan_review", []))
                 or [t("尚无可回顾的计划与行动关联。")])
            from ..plan_continuity import display_lines as prior_choice_lines
            card("先前的打算", prior_choice_lines(growth.get("prior_choices", []))
                 or [t("目前没有可供重新考虑的先前打算。")])
            card("她在意的事", [" · ".join(row.get("topic", "") for row in agency.get("interests", [])) or t("兴趣会从真实经历中慢慢长出来。")])
            card("你们之间", [t("聊过 {count} 次天", count=(bonds.get("owner") or {}).get("talks", 0))]
                 + ([t("以下为旧约定状态，尚未按具体成果核对。")] if bonds.get("promises") else [])
                 + [str(row.get("text", "")) + " · " + t(str(row.get("status", "pending"))) for row in bonds.get("promises", [])[-8:]])
            def reminder_line(row):
                due = row.get("due_on") or t("旧日页第 {number} 页", number=row.get("due_day", "—"))
                label = ("已写入本地对话" if row.get("said_via") == "local_transcript" else "用户标记已提醒") if row.get("due_on") and row.get("status") == "said" else str(row.get("status", "pending"))
                if row.get("due_on") and row.get("status") == "pending" and row["due_on"] < self.snapshot.get("date", ""):
                    label = "已过日期，待补充提醒"
                return due + " · " + row.get("text", "") + " · " + t(label)
            card("替你记着", [reminder_line(row) for row in states.get("hands", {}).get("reminders", [])]
                 or [t("还没有需要提醒的事。")], "remind")
            card("来过的朋友", [row.get("name", "") + " · " + t("已记录失联" if row.get("status") == "lost" else "本地来访记录")
                 for row in states.get("friends", {}).get("friends", [])] or [t("还没有朋友来访。")])
        elif section == "heart":
            from ..inner_sources import display_lines as inner_lines
            from ..inner_attempts import display_lines as inner_attempt_lines
            growth = states.get("development", {})
            attempts = [row for row in growth.get("inner_attempts", growth.get("outcomes", []))
                        if row.get("generation", {}).get("operation") == "inner"]
            if attempts:
                card("最近的内心整理", ["\n".join(inner_attempt_lines(row)) for row in reversed(attempts[-5:])])
            card("关于她自己", inner_lines(inner.get("narrative", {})) or [t("她还在慢慢认识自己。")])
            if inner.get("narrative_history"):
                card("以前怎样描述自己", ["\n".join(inner_lines(row, historical=True)) for row in inner["narrative_history"][-3:]])
            card("此刻的心意", [t("今天想安静一会儿") if inner.get("silence", {}).get("on") else t("可以慢慢说话。"), inner.get("silence", {}).get("note", "")])
            card("梦里的片段", ["\n".join(inner_lines(row)) for row in inner.get("dreams", [])[-5:]] or [t("还没有留下梦的片段。")])
            card("重新认识的事", ["\n".join(inner_lines(row)) for row in inner.get("corrections", [])[-6:]])
            card("值得记住的日子", [t("第 {number} 天", number=row.get("day", "—")) + " · " + row.get("name", "") for row in memorial.get("anniversaries", [])] or [t("重要的日子会慢慢积攒。")])
            card("还没放下的事", [row.get("text", "") for row in memorial.get("regrets", [])[-8:]] or [t("此刻没有留下遗憾。")])
            card("好好说过再见", [row.get("name", "") + " · " + row.get("note", "") for row in memorial.get("farewells", [])[-8:]])
            card("她不想聊的事", [str(row.get("topic", row.get("text", ""))) if isinstance(row, dict) else str(row) for row in agency.get("boundaries", [])])
        else:
            card("留下一点小作品", [t("有时是一首诗，有时是一封信，也可能是一幅字符画。")], "work")
            for work in reversed(states.get("works", {}).get("works", [])):
                card(work.get("title") or "无题", [t("第 {number} 天", number=work.get("day", "—")), work.get("text", "")])
            if len(rows) == 1:
                card("作品收藏", [t("她留下的作品，会好好收在这里。")])
        self.life.replace(rows)

    @Slot(int, int, int, int)
    def saveGeometry(self, width, height, horizontal, vertical):
        if self._ready:
            try:
                saved = read_json(ui_settings_path(), {})
                saved = saved if isinstance(saved, dict) else {}
                saved["quick_geometry"] = [width, height, horizontal, vertical]
                write_json_atomic(ui_settings_path(), saved)
            except OSError as error:
                self.notify(error, True)

    @Slot()
    def requestClose(self):
        self.stopPlugin()
        self._closing = True
        self._pulse.stop()
        self._watch.stop()
        self.stateChanged.emit()
        if not self._pending:
            self._finish_close()
        else:
            self.notify(t("正在保存窗口并等当前操作结束…"))

    def _finish_close(self):
        self._closing = False
        if self.session and not self.session.closed:
            self.submit("close", self.session.close, lambda result: self._closed_signal())
            self._closing = True
        else:
            self._closed_signal()

    def _closed_signal(self):
        self._closed = True
        self.closeReady.emit()

    def shutdown(self):
        self.stopPlugin()
        self._pulse.stop()
        self._watch.stop()
        self._executor.shutdown(wait=True)
        self._closed = True
        if self.session and not self.session.closed:
            self.session.close()
