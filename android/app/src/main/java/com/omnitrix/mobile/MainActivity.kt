package com.omnitrix.mobile

import android.os.Bundle
import android.content.Context
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.UUID

private val Bg = Color(0xFF0B1014)
private val Panel = Color(0xFF121A20)
private val Raised = Color(0xFF19252B)
private val Rule = Color(0xFF2A3940)
private val White = Color(0xFFEAF1F2)
private val Muted = Color(0xFF9BAEB6)
private val Mint = Color(0xFF91E6C4)
private val Amber = Color(0xFFFFCC7A)
private val ErrorRed = Color(0xFFFF8B8B)

private enum class Tab(val title: String, val glyph: String) {
    CHAT("Chat", "◉"), CODE("Workspace", "⌘"), STATUS("Status", "▤"), CONNECT("Connect", "⚙")
}
private data class ChatLine(val role: String, val text: String)
private data class FileItem(val name: String, val type: String, val bytes: Long = 0L)
private data class TestRun(
    val status: String, val count: Int?, val revision: String,
    val duration: Double?, val finished: String, val output: String
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(11, 16, 20)
        window.navigationBarColor = android.graphics.Color.rgb(11, 16, 20)
        setContent { OmnitrixApp() }
    }
}

internal object RuntimeInputValidation {
    fun normalizeStudioUrl(raw: String): String {
        val normalized = raw.trim().trimEnd('/')
        require(normalized.startsWith("https://")) { "Use the HTTPS URL for Studio port 8000." }
        require(!normalized.contains("@") && !normalized.contains("?") && !normalized.contains("#")) {
            "Enter only the base URL, without credentials or query parameters."
        }
        val parsed = URL(normalized)
        require(parsed.protocol == "https" && parsed.host.isNotBlank() && parsed.path.isNullOrEmpty()) {
            "Enter a valid HTTPS base URL without a path."
        }
        return normalized
    }

    fun validateRuntimeToken(raw: String): String {
        val value = raw.trim()
        require(value.length >= 24) { "The generated runtime token looks incomplete." }
        return value
    }
}

private class RuntimeClient(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context, "omnitrix_secure",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    var base: String = prefs.getString("url", "") ?: ""
        private set
    var token: String = prefs.getString("token", "") ?: ""
        private set

    fun configure(urlValue: String, tokenValue: String) {
        val value = RuntimeInputValidation.normalizeStudioUrl(urlValue)
        val checkedToken = RuntimeInputValidation.validateRuntimeToken(tokenValue)
        base = value
        token = checkedToken
        prefs.edit().putString("url", base).putString("token", token).apply()
    }

    fun disconnect() {
        token = ""
        prefs.edit().remove("token").apply()
    }

    fun ready() = base.isNotBlank() && token.isNotBlank()
    suspend fun get(route: String) = request("GET", route, null)
    suspend fun post(route: String, body: JSONObject) = request("POST", route, body)

    private suspend fun request(method: String, route: String, body: JSONObject?): JSONObject =
        withContext(Dispatchers.IO) {
            if (!ready()) throw IOException("Connect the runtime in Settings first.")
            val connection = (URL(base + route).openConnection() as HttpURLConnection)
            connection.requestMethod = method
            connection.connectTimeout = 12000
            connection.readTimeout = if (route == "/api/tests/run") 210000 else 25000
            connection.useCaches = false
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Authorization", "Bearer " + token)
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
            try {
                if (body != null) {
                    connection.outputStream.use { it.write(body.toString().toByteArray(StandardCharsets.UTF_8)) }
                }
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val text = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
                if (code !in 200..299) {
                    val detail = try { JSONObject(text).optString("error", "") } catch (_: Exception) { "" }
                    throw IOException(if (detail.isBlank()) "Studio returned HTTP " + code else detail)
                }
                JSONObject(text)
            } finally {
                connection.disconnect()
            }
        }
}

@Composable
private fun OmnitrixApp() {
    val context = LocalContext.current
    val api = remember { RuntimeClient(context) }
    val scope = rememberCoroutineScope()
    var tab by remember { mutableStateOf(Tab.CHAT) }
    var url by remember { mutableStateOf(api.base) }
    var token by remember { mutableStateOf(api.token) }
    var showToken by remember { mutableStateOf(false) }
    var connected by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var health by remember { mutableStateOf<JSONObject?>(null) }
    var tests by remember { mutableStateOf<TestRun?>(null) }
    var runningTests by remember { mutableStateOf(false) }
    val session = remember { UUID.randomUUID().toString() }
    val messages = remember { mutableStateListOf(ChatLine("assistant", "I'm Omnitrix. Connect the live Python runtime to start chatting. Offline demo text is never passed off as real model inference.") ) }
    var input by remember { mutableStateOf("") }
    var folder by remember { mutableStateOf(".") }
    var files by remember { mutableStateOf<List<FileItem>>(emptyList()) }
    var filePath by remember { mutableStateOf<String?>(null) }
    var draft by remember { mutableStateOf("") }
    var original by remember { mutableStateOf("") }
    var fileHash by remember { mutableStateOf("") }
    var codeBusy by remember { mutableStateOf(false) }
    var codeNotice by remember { mutableStateOf("") }

    fun loadFolder(path: String) {
        scope.launch {
            codeBusy = true
            try {
                val response = api.get("/api/workspace/list?path=" + URLEncoder.encode(path, "UTF-8"))
                val output = response.optJSONObject("output") ?: throw IOException(response.optString("error", "Workspace list failed."))
                val array = output.optJSONArray("entries") ?: JSONArray()
                files = buildList {
                    for (i in 0 until array.length()) {
                        val item = array.optJSONObject(i) ?: continue
                        add(FileItem(item.optString("name"), item.optString("type"), item.optLong("size_bytes")))
                    }
                }
                codeNotice = "Workspace refreshed."
            } catch (e: Exception) {
                codeNotice = e.message ?: "Could not load workspace."
            } finally { codeBusy = false }
        }
    }

    fun connect() {
        scope.launch {
            busy = true
            error = ""
            try {
                api.configure(url, token)
                val result = api.get("/api/health")
                health = result
                connected = true
                tests = try { api.get("/api/tests/latest").optJSONObject("result")?.toTestRun() } catch (_: Exception) { null }
                error = "Connected · revision " + result.optString("revision", "unknown")
                loadFolder(folder)
            } catch (e: Exception) {
                connected = false
                error = e.message ?: "Connection failed."
            } finally { busy = false }
        }
    }

    LaunchedEffect(Unit) {
        if (api.ready()) {
            scope.launch {
                try {
                    health = api.get("/api/health")
                    connected = true
                    tests = api.get("/api/tests/latest").optJSONObject("result")?.toTestRun()
                    loadFolder(folder)
                } catch (e: Exception) {
                    connected = false
                    error = e.message ?: "Saved runtime is unreachable."
                }
            }
        }
    }

    MaterialTheme(colorScheme = darkColorScheme(primary = Mint, onPrimary = Bg, secondary = Amber, background = Bg, surface = Panel, onSurface = White, outline = Rule, error = ErrorRed)) {
        Scaffold(
            containerColor = Bg,
            contentWindowInsets = WindowInsets(0, 0, 0, 0),
            bottomBar = {
                Column {
                    HorizontalDivider(color = Rule)
                    NavigationBar(containerColor = Panel) {
                        Tab.entries.forEach { destination ->
                            NavigationBarItem(
                                selected = tab == destination,
                                onClick = { tab = destination },
                                icon = {
                                    Box(Modifier.size(28.dp).background(if (tab == destination) Mint.copy(alpha = .15f) else Color.Transparent, RoundedCornerShape(8.dp)), contentAlignment = Alignment.Center) {
                                        Text(destination.glyph, color = if (tab == destination) Mint else Muted, fontSize = 16.sp)
                                    }
                                },
                                label = { Text(destination.title, fontSize = 10.sp) }
                            )
                        }
                    }
                }
            }
        ) { padding ->
            Box(Modifier.fillMaxSize().background(Bg).padding(padding)) {
                when (tab) {
                    Tab.CHAT -> ChatScreen(
                        messages, input, connected, busy,
                        health?.optString("provider_mode", "unknown") ?: "disconnected",
                        { input = it },
                        {
                            val prompt = input.trim()
                            if (connected && prompt.isNotEmpty() && !busy) {
                                messages.add(ChatLine("user", prompt))
                                input = ""
                                busy = true
                                scope.launch {
                                    try {
                                        val response = api.post("/api/chat", JSONObject().put("message", prompt).put("session_id", session))
                                        messages.add(ChatLine("assistant", response.optString("reply", "Runtime returned no response text.")))
                                    } catch (e: Exception) { messages.add(ChatLine("system", e.message ?: "Chat failed.")) }
                                    finally { busy = false }
                                }
                            }
                        },
                        { tab = Tab.CONNECT }
                    )
                    Tab.CODE -> WorkspaceScreen(
                        connected, folder, files, filePath, draft, original, codeBusy,
                        health?.optBoolean("workspace_write_enabled") == true,
                        codeNotice,
                        { tab = Tab.CONNECT },
                        { loadFolder(folder) },
                        { item ->
                            val path = if (folder == ".") item.name else folder + "/" + item.name
                            if (item.type == "directory") {
                                folder = path
                                filePath = null
                                loadFolder(path)
                            } else {
                                scope.launch {
                                    codeBusy = true
                                    try {
                                        val result = api.get("/api/workspace/read?path=" + URLEncoder.encode(path, "UTF-8"))
                                        val output = result.optJSONObject("output") ?: throw IOException(result.optString("error", "Read failed."))
                                        filePath = path
                                        draft = output.optString("content", "")
                                        original = draft
                                        fileHash = output.optString("sha256", "")
                                        codeNotice = "Opened " + path
                                    } catch (e: Exception) { codeNotice = e.message ?: "Read failed." }
                                    finally { codeBusy = false }
                                }
                            }
                        },
                        {
                            if (filePath != null) {
                                filePath = null; draft = ""; original = ""; fileHash = ""
                            } else {
                                folder = if (!folder.contains('/')) "." else folder.substringBeforeLast('/')
                                loadFolder(folder)
                            }
                        },
                        { draft = it },
                        {
                            val path = filePath
                            if (path != null && draft != original && fileHash.isNotBlank()) {
                                scope.launch {
                                    codeBusy = true
                                    try {
                                        val savedResponse = api.post("/api/workspace/write", JSONObject().put("path", path).put("content", draft).put("expected_sha256", fileHash))
                                        val saved = savedResponse.optJSONObject("result") ?: throw IOException("The runtime returned no save receipt.")
                                        fileHash = saved.optString("sha256", fileHash)
                                        original = draft
                                        health = api.get("/api/health")
                                        codeNotice = "Saved. Tests have not been run automatically."
                                    } catch (e: Exception) { codeNotice = e.message ?: "Save failed." }
                                    finally { codeBusy = false }
                                }
                            }
                        }
                    )
                    Tab.STATUS -> StatusScreen(
                        connected, busy, health, tests, runningTests, error,
                        { tab = Tab.CONNECT },
                        {
                            scope.launch {
                                busy = true
                                try { health = api.get("/api/health"); tests = api.get("/api/tests/latest").optJSONObject("result")?.toTestRun(); error = "" }
                                catch (e: Exception) { error = e.message ?: "Refresh failed." }
                                finally { busy = false }
                            }
                        },
                        {
                            scope.launch {
                                runningTests = true
                                try {
                                    tests = api.post("/api/tests/run", JSONObject()).toTestRun()
                                    health = api.get("/api/health")
                                    error = "Test run completed. Review the recorded result below."
                                } catch (e: Exception) { error = e.message ?: "Test run failed." }
                                finally { runningTests = false }
                            }
                        }
                    )
                    Tab.CONNECT -> ConnectScreen(
                        url, token, showToken, connected, busy, error,
                        { url = it }, { token = it }, { showToken = !showToken }, { connect() },
                        {
                            api.disconnect()
                            token = ""
                            connected = false
                            health = null
                            error = "Saved token removed from this device."
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun Header(title: String, detail: String, online: Boolean) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 15.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).background(Mint, RoundedCornerShape(10.dp)), contentAlignment = Alignment.Center) {
                Text("O", color = Bg, fontSize = 20.sp, fontWeight = FontWeight.Black)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("OMNITRIX", color = White, fontWeight = FontWeight.Black, letterSpacing = 2.sp, fontSize = 15.sp)
                Text("PERSONAL AI SYSTEM", color = Muted, fontSize = 9.sp, letterSpacing = 1.2.sp)
            }
            Row(Modifier.background(if (online) Mint.copy(alpha = .12f) else Amber.copy(alpha = .12f), CircleShape).padding(horizontal = 9.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(6.dp).background(if (online) Mint else Amber, CircleShape))
                Spacer(Modifier.width(6.dp))
                Text(if (online) "ONLINE" else "OFFLINE", color = if (online) Mint else Amber, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            }
        }
        Spacer(Modifier.height(20.dp))
        Text(title, color = White, fontSize = 25.sp, fontWeight = FontWeight.Bold)
        Text(detail, color = Muted, fontSize = 12.sp, lineHeight = 18.sp)
    }
}

@Composable
private fun ChatScreen(messages: List<ChatLine>, input: String, connected: Boolean, busy: Boolean, mode: String, onInput: (String) -> Unit, onSend: () -> Unit, onConnect: () -> Unit) {
    Column(Modifier.fillMaxSize()) {
        Header("Talk to Omnitrix", "One orchestrator · transparent runtime state", connected)
        Row(Modifier.fillMaxWidth().padding(horizontal = 15.dp).background(Panel, RoundedCornerShape(10.dp)).padding(11.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("MODEL MODE", color = Muted, fontSize = 9.sp, letterSpacing = 1.2.sp)
                Text(if (!connected) "Runtime not connected" else if (mode == "offline-demo") "OFFLINE DEMO · simulated" else "Configured model adapter", color = if (!connected || mode == "offline-demo") Amber else Mint, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
            }
            if (!connected) TextButton(onClick = onConnect) { Text("Connect →", color = Mint) }
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth().padding(horizontal = 13.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(messages) { line ->
                val user = line.role == "user"
                val system = line.role == "system"
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = if (user) Arrangement.End else Arrangement.Start
                ) {
                    Column(
                        Modifier.fillMaxWidth(if (user) .9f else 1f)
                            .background(if (user) Color(0xFF1B3731) else if (system) Color(0xFF392423) else Raised, RoundedCornerShape(15.dp))
                            .padding(13.dp)
                    ) {
                    Text(if (user) "YOU" else if (system) "RUNTIME ERROR" else "OMNITRIX", color = if (user) Mint else if (system) ErrorRed else Muted, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
                    Spacer(Modifier.height(5.dp))
                    Text(line.text, color = White, fontSize = 14.sp, lineHeight = 21.sp)
                    }
                }
            }
            if (busy) item { Text("Omnitrix is working…", color = Mint, modifier = Modifier.padding(8.dp)) }
        }
        Column(Modifier.fillMaxWidth().background(Panel).imePadding().padding(11.dp)) {
            OutlinedTextField(input, onInput, modifier = Modifier.fillMaxWidth(), enabled = connected && !busy, placeholder = { Text(if (connected) "Message Omnitrix…" else "Connect the runtime to start") }, maxLines = 5, shape = RoundedCornerShape(13.dp))
            Spacer(Modifier.height(7.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Outputs are not verified until checked.", color = Muted, fontSize = 9.sp, modifier = Modifier.weight(1f))
                Button(onSend, enabled = connected && !busy && input.isNotBlank(), colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Bg)) { Text(if (busy) "Working…" else "Send ↑") }
            }
        }
    }
}

@Composable
private fun WorkspaceScreen(
    connected: Boolean, folder: String, files: List<FileItem>, filePath: String?, draft: String, original: String, busy: Boolean,
    writeEnabled: Boolean, notice: String, onConnect: () -> Unit, onRefresh: () -> Unit, onOpen: (FileItem) -> Unit,
    onBack: () -> Unit, onDraft: (String) -> Unit, onSave: () -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        Header("Workspace", "Browse and edit existing files in the live Codespace checkout.", connected)
        if (!connected) {
            EmptyCard("Runtime not connected", "Connect Studio to browse files from the real repository.", "OPEN CONNECT", onConnect)
        } else if (filePath != null) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onBack) { Text("← Files", color = Mint) }
                Column(Modifier.weight(1f)) {
                    Text(filePath, color = White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text(if (draft == original) "No unsaved changes" else "UNSAVED CHANGES", color = if (draft == original) Muted else Amber, fontSize = 10.sp)
                }
            }
            OutlinedTextField(
                draft, onDraft,
                modifier = Modifier.fillMaxWidth().weight(1f).padding(horizontal = 12.dp, vertical = 7.dp),
                enabled = writeEnabled && !busy,
                minLines = 10, maxLines = Int.MAX_VALUE,
                textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace, lineHeight = 17.sp),
                shape = RoundedCornerShape(12.dp)
            )
            if (!writeEnabled) Text("File saving is not enabled by this runtime.", color = Amber, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 15.dp))
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onBack, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Raised, contentColor = White)) { Text("Close") }
                Button(onClick = onSave, enabled = writeEnabled && !busy && draft != original, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Bg)) { Text(if (busy) "Saving…" else "Save file") }
            }
            Text("Saves to the connected workspace only; it does not commit or push to GitHub.", color = Muted, fontSize = 9.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 3.dp))
        } else {
            Row(Modifier.fillMaxWidth().padding(horizontal = 13.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("LIVE FILE TREE", color = Mint, fontWeight = FontWeight.Bold, fontSize = 9.sp, letterSpacing = 1.2.sp)
                    Text("/" + if (folder == ".") "" else folder, color = White, fontSize = 12.sp)
                }
                TextButton(onClick = onBack, enabled = folder != "." && !busy) { Text("↑ Up", color = Mint) }
                TextButton(onClick = onRefresh, enabled = !busy) { Text("↻", color = Mint) }
            }
            if (notice.isNotBlank()) Text(notice, color = Muted, fontSize = 10.sp, modifier = Modifier.padding(horizontal = 15.dp, vertical = 4.dp))
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                if (files.isEmpty() && !busy) item { Text("No visible files in this folder.", color = Muted, modifier = Modifier.padding(18.dp)) }
                items(files, key = { it.name }) { item ->
                    Row(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(10.dp)).clickable(enabled = !busy) { onOpen(item) }.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(if (item.type == "directory") "▸" else "◇", color = if (item.type == "directory") Mint else Amber, fontSize = 17.sp)
                        Spacer(Modifier.width(11.dp))
                        Column(Modifier.weight(1f)) {
                            Text(item.name, color = White, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                            Text(if (item.type == "directory") "FOLDER" else readableSize(item.bytes), color = Muted, fontSize = 9.sp)
                        }
                        Text(if (item.type == "directory") "OPEN →" else "EDIT →", color = Muted, fontSize = 9.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusScreen(
    connected: Boolean, busy: Boolean, health: JSONObject?, tests: TestRun?, running: Boolean, error: String,
    onConnect: () -> Unit, onRefresh: () -> Unit, onRun: () -> Unit
) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Header("Tests & status", "Real runtime health and automated test evidence.", connected)
        if (!connected) EmptyCard("No live evidence", "This page does not invent a test status. Connect the runtime to retrieve real results.", "CONNECT RUNTIME", onConnect)
        else Column(Modifier.padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metric("BACKEND", "ONLINE", Mint, Modifier.weight(1f))
                Metric("MODEL MODE", health?.optString("provider_mode", "unknown")?.uppercase()?.replace("-", " ") ?: "UNKNOWN", if (health?.optString("provider_mode") == "offline-demo") Amber else Mint, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metric("REVISION", health?.optString("revision", "unknown") ?: "unknown", White, Modifier.weight(1f))
                Metric("WORKTREE", if (health?.optBoolean("working_tree_dirty") == true) "MODIFIED" else "CLEAN / UNKNOWN", if (health?.optBoolean("working_tree_dirty") == true) Amber else Muted, Modifier.weight(1f))
            }
            Card(colors = CardDefaults.cardColors(containerColor = Panel), border = BorderStroke(1.dp, Rule), shape = RoundedCornerShape(14.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Text("AUTOMATED PYTHON TESTS", color = Muted, fontSize = 10.sp, letterSpacing = 1.1.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(9.dp))
                    if (tests == null) Text("No result has been returned by this runtime yet.", color = Muted, fontSize = 12.sp)
                    else {
                        Text(tests.status.uppercase(), color = when (tests.status) { "passed" -> Mint; "failed", "timed_out" -> ErrorRed; else -> Amber }, fontSize = 23.sp, fontWeight = FontWeight.Black)
                        Text((tests.count?.toString() ?: "Unknown") + " tests · " + tests.revision + (tests.duration?.let { " · " + "%.1f".format(it) + "s" } ?: ""), color = Muted, fontSize = 11.sp)
                        if (tests.finished.isNotBlank()) Text("Finished " + tests.finished, color = Muted, fontSize = 9.sp)
                        Spacer(Modifier.height(10.dp))
                        if (tests.output.isNotBlank()) Text(tests.output.takeLast(6500), color = White, fontFamily = FontFamily.Monospace, fontSize = 9.sp, lineHeight = 14.sp)
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onRefresh, enabled = !busy && !running, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Raised, contentColor = White)) { Text("Refresh status") }
                Button(onRun, enabled = health?.optBoolean("tests_enabled") == true && !busy && !running, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Bg)) { Text(if (running) "Running…" else "Run test suite") }
            }
            Card(colors = CardDefaults.cardColors(containerColor = Panel), border = BorderStroke(1.dp, Rule), shape = RoundedCornerShape(14.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Text("RUNTIME PERMISSIONS", color = Muted, fontSize = 10.sp, letterSpacing = 1.1.sp, fontWeight = FontWeight.Bold)
                    StatusLine("Workspace reading", yesNo(health?.optBoolean("workspace_read_enabled")))
                    StatusLine("Workspace writing", yesNo(health?.optBoolean("workspace_write_enabled")))
                    StatusLine("Auto-sync with main", yesNo(health?.optBoolean("auto_sync_main_enabled")))
                    StatusLine("Sync state", health?.optString("sync_status", "unknown") ?: "unknown")
                    StatusLine("Branch", health?.optString("code_branch", "unknown") ?: "unknown")
                }
            }
            if (error.isNotBlank()) Text(error, color = if (connected) Mint else ErrorRed, fontSize = 11.sp)
        }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun ConnectScreen(
    url: String, token: String, showToken: Boolean, connected: Boolean, busy: Boolean, message: String,
    onUrl: (String) -> Unit, onToken: (String) -> Unit, onToggle: () -> Unit, onConnect: () -> Unit, onDisconnect: () -> Unit
) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Header("Connect runtime", "Pair this app with the Python Studio backend once.", connected)
        Column(Modifier.padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Card(colors = CardDefaults.cardColors(containerColor = Panel), border = BorderStroke(1.dp, Rule), shape = RoundedCornerShape(14.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Text("STUDIO PORT URL", color = Muted, fontWeight = FontWeight.Bold, fontSize = 9.sp, letterSpacing = 1.1.sp)
                    OutlinedTextField(url, onUrl, modifier = Modifier.fillMaxWidth(), placeholder = { Text("https://your-codespace-8000.app.github.dev") }, singleLine = true, shape = RoundedCornerShape(11.dp))
                    Spacer(Modifier.height(10.dp))
                    Text("RUNTIME TOKEN", color = Muted, fontWeight = FontWeight.Bold, fontSize = 9.sp, letterSpacing = 1.1.sp)
                    OutlinedTextField(token, onToken, modifier = Modifier.fillMaxWidth(), placeholder = { Text("Paste generated runtime token") }, visualTransformation = if (showToken) VisualTransformation.None else PasswordVisualTransformation(), trailingIcon = { TextButton(onClick = onToggle) { Text(if (showToken) "Hide" else "Show", color = Mint) } }, singleLine = true, shape = RoundedCornerShape(11.dp))
                    Spacer(Modifier.height(12.dp))
                    Button(onConnect, enabled = !busy && url.isNotBlank() && token.isNotBlank(), modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Bg), shape = RoundedCornerShape(11.dp)) { Text(if (busy) "Connecting…" else "Save securely & connect") }
                    if (connected) TextButton(onDisconnect) { Text("Disconnect and remove saved token", color = ErrorRed) }
                    if (message.isNotBlank()) Text(message, color = if (connected) Mint else Amber, fontSize = 11.sp)
                }
            }
            Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(14.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Text("SETUP ONCE", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
                    Spacer(Modifier.height(8.dp))
                    Step("01", "Start the Omnitrix Studio Codespace. Its devcontainer starts the Python backend automatically.")
                    Step("02", "In Ports, copy the forwarded URL for port 8000.")
                    Step("03", "Copy the runtime token printed by Studio and paste it here. Never share or commit it.")
                    Step("04", "Then use the Chat, Workspace and Status tabs in this app; no CLI is needed for chatting or running tests.")
                    Spacer(Modifier.height(8.dp))
                    Text("Workspace edits save to the live checkout but are not committed or pushed automatically. The default model profile is an offline simulation, not live inference.", color = Amber, fontSize = 11.sp, lineHeight = 16.sp)
                }
            }
        }
    }
}

@Composable
private fun EmptyCard(title: String, body: String, action: String, onAction: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp).background(Panel, RoundedCornerShape(14.dp)).padding(16.dp)) {
        Text(title, color = White, fontWeight = FontWeight.Bold, fontSize = 16.sp)
        Spacer(Modifier.height(6.dp))
        Text(body, color = Muted, fontSize = 12.sp, lineHeight = 18.sp)
        Spacer(Modifier.height(12.dp))
        Button(onAction, colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Bg)) { Text(action) }
    }
}

@Composable
private fun Metric(title: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Column(modifier.background(Panel, RoundedCornerShape(12.dp)).padding(12.dp)) {
        Text(title, color = Muted, fontSize = 9.sp, letterSpacing = .8.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(7.dp))
        Text(value, color = color, fontSize = 13.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun StatusLine(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Muted, fontSize = 11.sp, modifier = Modifier.weight(1f))
        Text(value, color = if (value == "enabled") Mint else if (value == "disabled") Amber else White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun Step(number: String, description: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
        Text(number, color = Mint, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        Text(description, color = Muted, fontSize = 11.sp, lineHeight = 16.sp)
    }
}

private fun JSONObject.toTestRun() = TestRun(
    status = optString("status", "unknown"),
    count = if (has("test_count") && !isNull("test_count")) optInt("test_count") else null,
    revision = optString("revision", "unknown"),
    duration = if (has("duration_seconds") && !isNull("duration_seconds")) optDouble("duration_seconds") else null,
    finished = optString("finished_at", ""),
    output = optString("output", "")
)
private fun yesNo(value: Boolean?) = when (value) { true -> "enabled"; false -> "disabled"; null -> "unknown" }
private fun readableSize(size: Long) = if (size < 1024) "$size B" else if (size < 1024 * 1024) "%.1f KB".format(size / 1024.0) else "%.1f MB".format(size / (1024.0 * 1024.0))
