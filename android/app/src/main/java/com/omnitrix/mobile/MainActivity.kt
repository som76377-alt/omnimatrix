package com.omnitrix.mobile

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.util.Base64
import java.util.UUID

private val Black = Color(0xFF050605)
private val Surface = Color(0xFF101210)
private val SurfaceRaised = Color(0xFF171A16)
private val Green = Color(0xFFB8FF42)
private val White = Color(0xFFF1F3EC)
private val Grey = Color(0xFF9A9E94)
private val Red = Color(0xFFFF6B6B)
private val Mono = FontFamily.Monospace
private const val REPOSITORY = "som76377-alt/omnimatrix"

private enum class AppTab(val title: String) {
    CHAT("Chat"), REPO("Repo"), STATUS("Runs"), ACCOUNT("Account")
}
private data class ChatMessage(val role: String, val text: String)
private data class RepoEntry(val name: String, val path: String, val type: String, val size: Long, val sha: String)
private data class CiRun(val title: String, val status: String, val branch: String, val url: String, val updated: String)
private data class DeviceLogin(
    val deviceCode: String,
    val userCode: String,
    val verificationUri: String,
    val intervalSeconds: Int,
    val expiresInSeconds: Int
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(5, 6, 5)
        window.navigationBarColor = android.graphics.Color.rgb(5, 6, 5)
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
        val value = raw.filterNot { it.isWhitespace() }
        require(value.length >= 24) { "The runtime token looks incomplete." }
        require(value.all {
            it in 'a'..'z' || it in 'A'..'Z' || it in '0'..'9' || it == '-' || it == '_'
        }) { "The token contains unsupported characters. Copy the token value only." }
        return value
    }
}

internal object GitHubInputValidation {
    fun normalizeClientId(raw: String): String {
        val value = raw.trim()
        require(value.length in 10..160 && value.all {
            it in 'a'..'z' || it in 'A'..'Z' || it in '0'..'9' || it == '.' || it == '_' || it == '-'
        }) { "Enter the Client ID from your GitHub OAuth App." }
        return value
    }

    fun isSafeRepoPath(path: String): Boolean {
        if (path.isBlank() || path.startsWith("/") || path.contains("\\") || path.contains("\u0000")) return false
        val parts = path.split("/")
        if (parts.any { it.isBlank() || it == "." || it == ".." || it.startsWith(".") }) return false
        if (parts.any { Regex("(secret|token|password|api[_-]?key|credential|private[_-]?key)", RegexOption.IGNORE_CASE).containsMatchIn(it) }) return false
        return parts.first() in setOf("core", "interfaces", "tests", "docs", "config", "webapp", "android", "README.md")
    }
}

private class GitHubClient(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context, "omnitrix_github_secure",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    var clientId: String = prefs.getString("client_id", "") ?: ""
        private set
    var accessToken: String = prefs.getString("access_token", "") ?: ""
        private set
    var username: String = prefs.getString("username", "") ?: ""
        private set

    fun ready() = accessToken.isNotBlank()
    fun saveClientId(value: String) {
        clientId = GitHubInputValidation.normalizeClientId(value)
        prefs.edit().putString("client_id", clientId).apply()
    }
    fun signOut() {
        accessToken = ""
        username = ""
        prefs.edit().remove("access_token").remove("username").apply()
    }

    suspend fun beginDeviceLogin(): DeviceLogin = withContext(Dispatchers.IO) {
        val id = GitHubInputValidation.normalizeClientId(clientId)
        val body = form(mapOf("client_id" to id, "scope" to "public_repo read:user"))
        val json = JSONObject(requestRaw(
            "POST", "https://github.com/login/device/code", body,
            contentType = "application/x-www-form-urlencoded; charset=utf-8", accept = "application/json"
        ))
        if (json.has("error")) throw IOException(json.optString("error_description", json.optString("error")))
        DeviceLogin(
            deviceCode = json.getString("device_code"),
            userCode = json.getString("user_code"),
            verificationUri = json.optString("verification_uri", "https://github.com/login/device"),
            intervalSeconds = json.optInt("interval", 5).coerceAtLeast(5),
            expiresInSeconds = json.optInt("expires_in", 900).coerceAtLeast(60)
        )
    }

    suspend fun authorizeDevice(device: DeviceLogin, onStatus: (String) -> Unit) {
        var waitSeconds = device.intervalSeconds
        val expiresAt = System.currentTimeMillis() + device.expiresInSeconds * 1000L
        while (System.currentTimeMillis() < expiresAt) {
            delay(waitSeconds * 1000L)
            val body = form(mapOf(
                "client_id" to clientId,
                "device_code" to device.deviceCode,
                "grant_type" to "urn:ietf:params:oauth:grant-type:device_code"
            ))
            val result = try {
                JSONObject(withContext(Dispatchers.IO) {
                    requestRaw("POST", "https://github.com/login/oauth/access_token", body,
                        contentType = "application/x-www-form-urlencoded; charset=utf-8", accept = "application/json")
                })
            } catch (e: Exception) {
                onStatus(e.message ?: "Waiting for GitHub authorization…")
                continue
            }
            val problem = result.optString("error", "")
            when (problem) {
                "authorization_pending" -> onStatus("Waiting for approval in GitHub…")
                "slow_down" -> {
                    waitSeconds += 5
                    onStatus("GitHub asked us to slow down. Still waiting…")
                }
                "access_denied" -> throw IOException("GitHub authorization was declined.")
                "expired_token" -> throw IOException("That sign-in code expired. Start again.")
                "" -> {
                    val value = result.optString("access_token", "")
                    if (value.isBlank()) throw IOException("GitHub returned no access token.")
                    withContext(Dispatchers.IO) {
                        accessToken = value
                        prefs.edit().putString("access_token", value).apply()
                    }
                    val viewer = getJson("/user")
                    username = viewer.optString("login", "")
                    prefs.edit().putString("username", username).apply()
                    return
                }
                else -> throw IOException(result.optString("error_description", problem))
            }
        }
        throw IOException("The sign-in code expired. Start again.")
    }

    suspend fun listContents(path: String): List<RepoEntry> {
        if (path.isNotBlank() && !GitHubInputValidation.isSafeRepoPath(path)) throw IOException("That repository path is not available in the app.")
        val encoded = if (path.isBlank()) "" else path.split("/").joinToString("/") { encodePathPart(it) }
        val json = getJson("/repos/" + REPOSITORY + "/contents" + if (encoded.isBlank()) "" else "/$encoded" + "?ref=main")
        val array = if (json.has("entries")) json.optJSONArray("entries") else null
        val entriesJson = if (json.has("type")) JSONArray().put(json) else arrayFrom(json)
        return buildList {
            for (i in 0 until entriesJson.length()) {
                val item = entriesJson.optJSONObject(i) ?: continue
                val itemPath = item.optString("path", "")
                val name = item.optString("name", "")
                val type = item.optString("type", "")
                if (name.isBlank() || name.startsWith(".") || !GitHubInputValidation.isSafeRepoPath(itemPath)) continue
                add(RepoEntry(name, itemPath, type, item.optLong("size"), item.optString("sha", "")))
            }
        }.sortedWith(compareBy<RepoEntry> { if (it.type == "dir") 0 else 1 }.thenBy { it.name.lowercase() })
    }

    suspend fun readFile(path: String): Pair<String, String> {
        if (!GitHubInputValidation.isSafeRepoPath(path)) throw IOException("That repository path is not available in the app.")
        val encoded = path.split("/").joinToString("/") { encodePathPart(it) }
        val json = getJson("/repos/" + REPOSITORY + "/contents/" + encoded + "?ref=main")
        if (json.optString("type") != "file") throw IOException("Choose a text file.")
        if (json.optLong("size") > 65536) throw IOException("This file is larger than the mobile editor's 64 KB limit.")
        val raw = json.optString("content", "")
        if (raw.isBlank()) throw IOException("GitHub did not return file contents.")
        val bytes = try { Base64.getMimeDecoder().decode(raw) } catch (_: Exception) { throw IOException("This file is not readable as UTF-8 text.") }
        val text = try { String(bytes, StandardCharsets.UTF_8) } catch (_: Exception) { throw IOException("This file is not UTF-8 text.") }
        if (text.contains('\u0000')) throw IOException("Binary files cannot be edited here.")
        return text to json.optString("sha", "")
    }

    suspend fun updateFile(path: String, content: String, sha: String): String {
        if (!GitHubInputValidation.isSafeRepoPath(path)) throw IOException("That repository path is not writable from the app.")
        if (content.toByteArray(StandardCharsets.UTF_8).size > 65536) throw IOException("Keep mobile edits under 64 KB.")
        if (sha.isBlank()) throw IOException("No original file SHA is available. Reload before saving.")
        val encodedPath = path.split("/").joinToString("/") { encodePathPart(it) }
        val jsonBody = JSONObject()
            .put("message", "Edit " + path + " from Omnitrix Android")
            .put("content", Base64.getEncoder().encodeToString(content.toByteArray(StandardCharsets.UTF_8)))
            .put("sha", sha)
            .put("branch", "main")
        val result = requestJson("PUT", "/repos/" + REPOSITORY + "/contents/" + encodedPath, jsonBody)
        return result.optJSONObject("content")?.optString("sha", "") ?: ""
    }

    suspend fun recentRuns(): List<CiRun> {
        val root = getJson("/repos/" + REPOSITORY + "/actions/runs?per_page=8")
        val items = root.optJSONArray("workflow_runs") ?: JSONArray()
        return buildList {
            for (i in 0 until items.length()) {
                val item = items.optJSONObject(i) ?: continue
                val status = item.optString("conclusion").takeIf { it.isNotBlank() && it != "null" }
                    ?: item.optString("status", "unknown")
                add(CiRun(
                    title = item.optString("display_title", item.optString("name", "Workflow")),
                    status = status.replace("_", " "),
                    branch = item.optString("head_branch", "main"),
                    url = item.optString("html_url", "https://github.com/" + REPOSITORY + "/actions"),
                    updated = item.optString("updated_at", "")
                ))
            }
        }
    }

    private suspend fun getJson(path: String) = requestJson("GET", path, null)

    private suspend fun requestJson(method: String, path: String, body: JSONObject?): JSONObject = withContext(Dispatchers.IO) {
        if (!ready()) throw IOException("Sign in with GitHub first.")
        val full = if (path.startsWith("https://")) path else "https://api.github.com" + path
        val content = body?.toString()
        JSONObject(requestRaw(method, full, content, accessToken, "application/json; charset=utf-8", "application/vnd.github+json"))
    }

    private fun arrayFrom(json: JSONObject): JSONArray {
        val array = JSONArray()
        json.keys().forEach { key ->
            val value = json.opt(key)
            if (value is JSONObject) array.put(value)
        }
        return array
    }

    private fun encodePathPart(value: String) = URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    private fun form(values: Map<String, String>) = values.entries.joinToString("&") {
        URLEncoder.encode(it.key, "UTF-8") + "=" + URLEncoder.encode(it.value, "UTF-8")
    }

    private fun requestRaw(
        method: String, address: String, body: String?, bearer: String? = null,
        contentType: String = "application/json; charset=utf-8", accept: String = "application/vnd.github+json"
    ): String {
        val connection = URL(address).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 15000
        connection.readTimeout = 25000
        connection.useCaches = false
        connection.setRequestProperty("User-Agent", "Omnitrix-Android")
        connection.setRequestProperty("Accept", accept)
        connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
        if (!bearer.isNullOrBlank()) connection.setRequestProperty("Authorization", "Bearer " + bearer.trim())
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", contentType)
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body.toByteArray(StandardCharsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val detail = try { JSONObject(text).optString("message", JSONObject(text).optString("error_description", "")) } catch (_: Exception) { "" }
                throw IOException(if (detail.isBlank()) "GitHub returned HTTP " + code else detail)
            }
            return text
        } finally {
            connection.disconnect()
        }
    }
}

private class RuntimeClient(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context, "omnitrix_runtime_secure",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    var base: String = prefs.getString("url", "") ?: ""
        private set
    var token: String = prefs.getString("token", "") ?: ""
        private set

    fun configure(urlValue: String, tokenValue: String) {
        base = RuntimeInputValidation.normalizeStudioUrl(urlValue)
        token = RuntimeInputValidation.validateRuntimeToken(tokenValue)
        prefs.edit().putString("url", base).putString("token", token).apply()
    }
    fun ready() = base.isNotBlank() && token.isNotBlank()
    suspend fun get(route: String) = request("GET", route, null)
    suspend fun post(route: String, body: JSONObject) = request("POST", route, body)

    private suspend fun request(method: String, route: String, body: JSONObject?): JSONObject = withContext(Dispatchers.IO) {
        if (!ready()) throw IOException("Connect the Python chat runtime from Account.")
        val connection = URL(base + route).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 12000
        connection.readTimeout = if (route == "/api/tests/run") 210000 else 25000
        connection.useCaches = false
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("Authorization", "Bearer " + RuntimeInputValidation.validateRuntimeToken(token))
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(StandardCharsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val detail = try { JSONObject(text).optString("error", "") } catch (_: Exception) { "" }
                throw IOException(if (detail.isBlank()) "Runtime returned HTTP " + code else detail)
            }
            JSONObject(text)
        } finally { connection.disconnect() }
    }
}

@Composable
private fun OmnitrixApp() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val github = remember { GitHubClient(context) }
    val runtime = remember { RuntimeClient(context) }
    var tab by remember { mutableStateOf(AppTab.CHAT) }
    var clientId by remember { mutableStateOf(github.clientId) }
    var githubConnected by remember { mutableStateOf(github.ready()) }
    var username by remember { mutableStateOf(github.username) }
    var device by remember { mutableStateOf<DeviceLogin?>(null) }
    var authBusy by remember { mutableStateOf(false) }
    var authMessage by remember { mutableStateOf("") }
    var githubError by remember { mutableStateOf("") }
    var chatUrl by remember { mutableStateOf(runtime.base) }
    var chatToken by remember { mutableStateOf(runtime.token) }
    var showToken by remember { mutableStateOf(false) }
    var showRuntimeSetup by remember { mutableStateOf(false) }
    var runtimeConnected by remember { mutableStateOf(false) }
    var runtimeStatus by remember { mutableStateOf<JSONObject?>(null) }
    var chatBusy by remember { mutableStateOf(false) }
    var chatInput by remember { mutableStateOf("") }
    var messages by remember {
        mutableStateOf(listOf(ChatMessage("OMNITRIX", "A little less noise. A lot more signal.")))
    }
    val sessionId = remember { UUID.randomUUID().toString() }
    var repoPath by remember { mutableStateOf("") }
    var entries by remember { mutableStateOf<List<RepoEntry>>(emptyList()) }
    var selectedFile by remember { mutableStateOf<RepoEntry?>(null) }
    var fileDraft by remember { mutableStateOf("") }
    var fileOriginal by remember { mutableStateOf("") }
    var fileSha by remember { mutableStateOf("") }
    var repoBusy by remember { mutableStateOf(false) }
    var repoMessage by remember { mutableStateOf("") }
    var confirmCommit by remember { mutableStateOf(false) }
    var runs by remember { mutableStateOf<List<CiRun>>(emptyList()) }
    var runsBusy by remember { mutableStateOf(false) }
    var runsMessage by remember { mutableStateOf("") }

    fun loadRepo(path: String) {
        if (!githubConnected) {
            repoMessage = "Sign in with GitHub to open the repository."
            return
        }
        scope.launch {
            repoBusy = true
            repoMessage = ""
            selectedFile = null
            try {
                entries = github.listContents(path)
                repoPath = path
                repoMessage = if (entries.isEmpty()) "No visible files here." else ""
            } catch (e: Exception) {
                repoMessage = e.message ?: "Could not load this folder."
            } finally { repoBusy = false }
        }
    }

    fun openRepoEntry(entry: RepoEntry) {
        if (entry.type == "dir") {
            loadRepo(entry.path)
            return
        }
        scope.launch {
            repoBusy = true
            repoMessage = ""
            try {
                val result = github.readFile(entry.path)
                selectedFile = entry
                fileDraft = result.first
                fileOriginal = result.first
                fileSha = result.second
            } catch (e: Exception) {
                repoMessage = e.message ?: "Could not open file."
            } finally { repoBusy = false }
        }
    }

    fun saveRepoFile() {
        val entry = selectedFile ?: return
        scope.launch {
            repoBusy = true
            repoMessage = ""
            try {
                github.updateFile(entry.path, fileDraft, fileSha)
                fileOriginal = fileDraft
                val refreshed = github.readFile(entry.path)
                fileSha = refreshed.second
                repoMessage = "Committed to main."
            } catch (e: Exception) {
                repoMessage = e.message ?: "Commit failed."
            } finally { repoBusy = false; confirmCommit = false }
        }
    }

    fun loadRuns() {
        if (!githubConnected) {
            runsMessage = "Sign in with GitHub to see CI runs."
            return
        }
        scope.launch {
            runsBusy = true
            runsMessage = ""
            try { runs = github.recentRuns() }
            catch (e: Exception) { runsMessage = e.message ?: "Could not load workflow runs." }
            finally { runsBusy = false }
        }
    }

    fun connectRuntime() {
        scope.launch {
            chatBusy = true
            try {
                runtime.configure(chatUrl, chatToken)
                runtimeStatus = runtime.get("/api/health")
                runtimeConnected = true
                messages = messages + ChatMessage("SYSTEM", "Python chat runtime connected.")
            } catch (e: Exception) {
                runtimeConnected = false
                messages = messages + ChatMessage("SYSTEM", e.message ?: "Runtime connection failed.")
            } finally { chatBusy = false }
        }
    }

    LaunchedEffect(Unit) {
        if (githubConnected) {
            try {
                username = github.username
                loadRuns()
                loadRepo("")
            } catch (_: Exception) { }
        }
        if (runtime.ready()) {
            try {
                runtimeStatus = runtime.get("/api/health")
                runtimeConnected = true
            } catch (_: Exception) { runtimeConnected = false }
        }
    }

    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Green, onPrimary = Black, secondary = Green, background = Black,
            surface = Surface, onSurface = White, error = Red
        ),
        typography = Typography(defaultFontFamily = Mono)
    ) {
        Scaffold(
            containerColor = Black,
            contentWindowInsets = WindowInsets(0, 0, 0, 0),
            bottomBar = {
                Row(
                    Modifier.fillMaxWidth().background(Black).padding(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(5.dp)
                ) {
                    AppTab.entries.forEach { destination ->
                        Column(
                            Modifier.weight(1f).background(if (tab == destination) SurfaceRaised else Black, RoundedCornerShape(6.dp))
                                .clickable { tab = destination }.padding(vertical = 13.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(destination.title, fontSize = 14.sp, color = if (tab == destination) Green else Grey, fontWeight = if (tab == destination) FontWeight.Bold else FontWeight.Medium)
                        }
                    }
                }
            }
        ) { insets ->
            Box(Modifier.fillMaxSize().padding(insets).background(Black)) {
                when (tab) {
                    AppTab.CHAT -> ChatScreen(
                        messages, chatInput, runtimeConnected, chatBusy,
                        { chatInput = it },
                        {
                            val prompt = chatInput.trim()
                            if (runtimeConnected && prompt.isNotEmpty() && !chatBusy) {
                                messages = messages + ChatMessage("YOU", prompt)
                                chatInput = ""
                                chatBusy = true
                                scope.launch {
                                    try {
                                        val response = runtime.post("/api/chat", JSONObject().put("message", prompt).put("session_id", sessionId))
                                        messages = messages + ChatMessage("OMNITRIX", response.optString("reply", "No response text returned."))
                                    } catch (e: Exception) {
                                        messages = messages + ChatMessage("SYSTEM", e.message ?: "Chat request failed.")
                                    } finally { chatBusy = false }
                                }
                            }
                        },
                        { tab = AppTab.ACCOUNT; showRuntimeSetup = true }
                    )
                    AppTab.REPO -> RepoScreen(
                        githubConnected, repoPath, entries, selectedFile, fileDraft, fileOriginal, repoBusy, repoMessage,
                        { loadRepo(if (repoPath.contains("/")) repoPath.substringBeforeLast("/") else "") },
                        { loadRepo(repoPath) }, { openRepoEntry(it) }, { fileDraft = it },
                        { confirmCommit = true }, { tab = AppTab.ACCOUNT }
                    )
                    AppTab.STATUS -> StatusScreen(
                        githubConnected, runs, runsBusy, runsMessage,
                        { loadRuns() },
                        { url -> openExternal(context, url) },
                        { tab = AppTab.ACCOUNT }
                    )
                    AppTab.ACCOUNT -> AccountScreen(
                        githubConnected, username, clientId, authBusy, authMessage, githubError, device,
                        runtimeConnected, showRuntimeSetup, chatUrl, chatToken, showToken,
                        { clientId = it }, {
                            scope.launch {
                                authBusy = true
                                githubError = ""
                                authMessage = "Preparing secure GitHub sign-in…"
                                try {
                                    github.saveClientId(clientId)
                                    device = github.beginDeviceLogin()
                                    authMessage = "Your one-time code is ready. Open GitHub and approve access."
                                } catch (e: Exception) {
                                    githubError = e.message ?: "Could not start GitHub sign-in."
                                    device = null
                                } finally { authBusy = false }
                            }
                        },
                        {
                            val pending = device
                            if (pending != null && !authBusy) {
                                openExternal(context, pending.verificationUri)
                                scope.launch {
                                    authBusy = true
                                    githubError = ""
                                    authMessage = "Waiting for approval in GitHub…"
                                    try {
                                        github.authorizeDevice(pending) { authMessage = it }
                                        githubConnected = true
                                        username = github.username
                                        device = null
                                        authMessage = "Signed in as " + github.username
                                        loadRuns()
                                        loadRepo("")
                                    } catch (e: Exception) {
                                        githubError = e.message ?: "GitHub sign-in failed."
                                        device = null
                                    } finally { authBusy = false }
                                }
                            }
                        },
                        {
                            github.signOut()
                            githubConnected = false
                            username = ""
                            entries = emptyList()
                            runs = emptyList()
                            selectedFile = null
                            authMessage = "Signed out. No local drafts were uploaded."
                        },
                        { showRuntimeSetup = !showRuntimeSetup },
                        { chatUrl = it }, { chatToken = it }, { showToken = !showToken },
                        { connectRuntime() },
                        {
                            runtimeConnected = false
                            runtimeStatus = null
                            chatToken = ""
                        },
                        { openExternal(context, "https://github.com/settings/developers") }
                    )
                }
            }
        }

        if (confirmCommit) {
            AlertDialog(
                onDismissRequest = { confirmCommit = false },
                containerColor = Surface,
                title = { Text("Commit to main?", color = White, fontSize = 21.sp, fontWeight = FontWeight.Bold) },
                text = { Text("This saves the edited file directly to the public Omnitrix repository's main branch. It creates a Git commit; it is not just a local draft.", color = Grey, fontSize = 15.sp, lineHeight = 22.sp) },
                confirmButton = {
                    TextButton(onClick = { saveRepoFile() }) { Text("COMMIT FILE", color = Green, fontSize = 14.sp) }
                },
                dismissButton = {
                    TextButton(onClick = { confirmCommit = false }) { Text("CANCEL", color = White, fontSize = 14.sp) }
                }
            )
        }
    }
}

@Composable
private fun AppHeader(title: String, detail: String? = null, state: String? = null) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 22.dp).padding(top = 22.dp, bottom = 18.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("OMNITRIX", color = Green, fontSize = 14.sp, letterSpacing = 2.sp, fontWeight = FontWeight.Black)
            Spacer(Modifier.weight(1f))
            if (!state.isNullOrBlank()) Text(state, color = if (state == "ONLINE" || state == "LINKED") Green else Grey, fontSize = 12.sp)
        }
        Spacer(Modifier.height(20.dp))
        Text(title, color = White, fontSize = 27.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold)
        if (!detail.isNullOrBlank()) {
            Spacer(Modifier.height(5.dp))
            Text(detail, color = Grey, fontSize = 14.sp, lineHeight = 20.sp)
        }
    }
}

@Composable
private fun ChatScreen(
    messages: List<ChatMessage>, input: String, connected: Boolean, busy: Boolean,
    onInput: (String) -> Unit, onSend: () -> Unit, onConnect: () -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        AppHeader("Chat", state = if (connected) "ONLINE" else "OFFLINE")
        if (!connected) {
            Column(Modifier.padding(horizontal = 22.dp).fillMaxWidth().background(Surface, RoundedCornerShape(8.dp)).padding(17.dp)) {
                Text("CHAT RUNTIME NOT CONNECTED", color = White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(7.dp))
                Text("GitHub sign-in connects the repository. Live AI chat separately needs the Python Studio runtime.", color = Grey, fontSize = 14.sp, lineHeight = 21.sp)
                Spacer(Modifier.height(12.dp))
                PrimaryButton("SET UP CHAT", onConnect)
            }
        }
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth().padding(horizontal = 22.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
            contentPadding = PaddingValues(top = 14.dp, bottom = 18.dp)
        ) {
            items(messages) { message ->
                Column(Modifier.fillMaxWidth()) {
                    Text(message.role, color = if (message.role == "SYSTEM") Red else Green, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(5.dp))
                    Text(message.text, color = White, fontSize = 16.sp, lineHeight = 24.sp)
                }
            }
            if (busy) item { Text("Thinking…", color = Green, fontSize = 15.sp) }
        }
        Row(Modifier.fillMaxWidth().background(Surface).imePadding().padding(10.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TerminalField(
                value = input, onValueChange = onInput, placeholder = "Message Omnitrix",
                modifier = Modifier.weight(1f), singleLine = false, enabled = connected && !busy
            )
            PrimaryButton(if (busy) "WAIT" else "SEND", onSend, enabled = connected && !busy && input.isNotBlank(), modifier = Modifier.heightIn(min = 52.dp))
        }
    }
}

@Composable
private fun RepoScreen(
    connected: Boolean, folder: String, entries: List<RepoEntry>, selected: RepoEntry?, draft: String, original: String,
    busy: Boolean, message: String, onBack: () -> Unit, onRefresh: () -> Unit, onOpen: (RepoEntry) -> Unit,
    onDraft: (String) -> Unit, onCommit: () -> Unit, onSignIn: () -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        AppHeader("Repository", if (selected != null) selected.path else "som76377-alt / omnimatrix", if (connected) "LINKED" else "SIGN IN")
        when {
            !connected -> Column(Modifier.padding(horizontal = 22.dp).fillMaxWidth().background(Surface, RoundedCornerShape(8.dp)).padding(18.dp)) {
                Text("Your code, directly from GitHub.", color = White, fontSize = 19.sp, lineHeight = 25.sp)
                Spacer(Modifier.height(8.dp))
                Text("Sign in once. Browse tracked files and edit them without a Codespaces URL.", color = Grey, fontSize = 15.sp, lineHeight = 22.sp)
                Spacer(Modifier.height(16.dp))
                PrimaryButton("GO TO ACCOUNT", onSignIn)
            }
            selected != null -> {
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    QuietButton("BACK") { onBack() }
                    Spacer(Modifier.weight(1f))
                    if (draft != original) Text("UNSAVED", color = Green, fontSize = 13.sp)
                }
                TerminalField(
                    value = draft, onValueChange = onDraft, placeholder = "",
                    modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp).background(Surface, RoundedCornerShape(6.dp)),
                    singleLine = false, enabled = !busy, large = false
                )
                Text("Edits are drafts until you commit them.", color = Grey, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 7.dp))
                PrimaryButton(if (busy) "SAVING…" else "COMMIT TO MAIN", onCommit, enabled = !busy && draft != original, modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp))
            }
            else -> {
                Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(if (folder.isBlank()) "/ main" else "/ main / " + folder, color = Grey, fontSize = 14.sp, modifier = Modifier.weight(1f))
                    QuietButton("REFRESH", onRefresh)
                    if (folder.isNotBlank()) QuietButton("UP", onBack)
                }
                if (message.isNotBlank()) Text(message, color = if (message.contains("fail", true) || message.contains("error", true)) Red else Grey, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 22.dp, vertical = 8.dp))
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), contentPadding = PaddingValues(bottom = 16.dp)) {
                    if (busy) item { Text("Loading…", color = Green, fontSize = 15.sp, modifier = Modifier.padding(14.dp)) }
                    items(entries, key = { it.path }) { entry ->
                        Column(
                            Modifier.fillMaxWidth().clickable(enabled = !busy) { onOpen(entry) }.padding(horizontal = 8.dp, vertical = 14.dp)
                        ) {
                            Text(entry.name + if (entry.type == "dir") "/" else "", color = if (entry.type == "dir") Green else White, fontSize = 16.sp, lineHeight = 22.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusScreen(
    connected: Boolean, runs: List<CiRun>, busy: Boolean, message: String,
    onRefresh: () -> Unit, onOpen: (String) -> Unit, onSignIn: () -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        AppHeader("Runs", "Continuous integration from GitHub", if (connected) "LINKED" else "SIGN IN")
        if (!connected) {
            Column(Modifier.padding(horizontal = 22.dp).fillMaxWidth().background(Surface, RoundedCornerShape(8.dp)).padding(18.dp)) {
                Text("See what actually passed.", color = White, fontSize = 19.sp)
                Spacer(Modifier.height(7.dp))
                Text("This view shows real GitHub Actions runs, not a made-up local status.", color = Grey, fontSize = 15.sp, lineHeight = 22.sp)
                Spacer(Modifier.height(15.dp))
                PrimaryButton("GO TO ACCOUNT", onSignIn)
            }
        } else {
            Row(Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(if (busy) "Refreshing…" else "Latest runs", color = White, fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                QuietButton("REFRESH", onRefresh)
                QuietButton("OPEN GITHUB") { onOpen("https://github.com/" + REPOSITORY + "/actions") }
            }
            if (message.isNotBlank()) Text(message, color = if (message.contains("fail", true) || message.contains("error", true)) Red else Grey, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 22.dp, vertical = 8.dp))
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 22.dp), contentPadding = PaddingValues(bottom = 18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                items(runs) { run ->
                    Column(Modifier.fillMaxWidth().clickable { onOpen(run.url) }) {
                        Text(run.title, color = White, fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium)
                        Spacer(Modifier.height(4.dp))
                        Text(run.status.uppercase(), color = statusColor(run.status), fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        Text(run.branch, color = Grey, fontSize = 13.sp)
                    }
                }
                if (runs.isEmpty() && !busy) item { Text("No workflow runs returned yet.", color = Grey, fontSize = 15.sp) }
            }
        }
    }
}

@Composable
private fun AccountScreen(
    connected: Boolean, username: String, clientId: String, busy: Boolean, message: String, error: String, device: DeviceLogin?,
    runtimeConnected: Boolean, showRuntimeSetup: Boolean, runtimeUrl: String, runtimeToken: String, showToken: Boolean,
    onClientId: (String) -> Unit, onBeginSignIn: () -> Unit, onAuthorize: () -> Unit, onSignOut: () -> Unit,
    onToggleRuntime: () -> Unit, onRuntimeUrl: (String) -> Unit, onRuntimeToken: (String) -> Unit,
    onToggleToken: () -> Unit, onConnectRuntime: () -> Unit, onDisconnectRuntime: () -> Unit,
    onRegisterApp: () -> Unit
) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader("Account", "One sign-in for the repository", if (connected) "LINKED" else "NOT LINKED")
        Column(Modifier.padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(15.dp)) {
            if (connected) {
                Text("Connected as @" + username, color = White, fontSize = 19.sp, fontWeight = FontWeight.Bold)
                Text("Repository access is stored securely on this device.", color = Grey, fontSize = 14.sp, lineHeight = 21.sp)
                QuietButton("SIGN OUT", onSignOut)
            } else if (device != null) {
                Text("AUTHORIZE THIS DEVICE", color = Green, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                Text(device.userCode, color = Green, fontSize = 34.sp, letterSpacing = 2.sp, fontWeight = FontWeight.Black)
                Text("Open GitHub, enter this code, and approve Omnitrix. Return here after approval.", color = Grey, fontSize = 15.sp, lineHeight = 22.sp)
                PrimaryButton(if (busy) "WAITING FOR GITHUB…" else "OPEN GITHUB & CONTINUE", onAuthorize, enabled = !busy)
            } else {
                Text("GitHub sign-in", color = White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("Your first sign-in needs a GitHub OAuth App Client ID. This is public app configuration, not your password or a secret token.", color = Grey, fontSize = 15.sp, lineHeight = 22.sp)
                TerminalField(clientId, onClientId, "OAuth App Client ID", singleLine = true, capitalization = KeyboardCapitalization.None)
                QuietButton("OPEN GITHUB APP SETTINGS", onRegisterApp)
                Text("Request only the access you understand. Omnitrix uses public-repository access to read files and make commits to this repository.", color = Grey, fontSize = 14.sp, lineHeight = 21.sp)
                PrimaryButton(if (busy) "PREPARING…" else "SIGN IN WITH GITHUB", onBeginSignIn, enabled = !busy && clientId.isNotBlank())
            }
            if (message.isNotBlank()) Text(message, color = Green, fontSize = 14.sp, lineHeight = 20.sp)
            if (error.isNotBlank()) Text(error, color = Red, fontSize = 14.sp, lineHeight = 20.sp)

            Spacer(Modifier.height(8.dp))
            Text("CHAT RUNTIME", color = White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            Text(if (runtimeConnected) "Python Studio is connected." else "This is separate from GitHub repository access. The runtime needs to be running for chat.", color = Grey, fontSize = 14.sp, lineHeight = 21.sp)
            QuietButton(if (showRuntimeSetup) "HIDE RUNTIME SETTINGS" else "ADVANCED RUNTIME SETTINGS", onToggleRuntime)
            if (showRuntimeSetup) {
                Text("Studio port 8000 URL", color = Grey, fontSize = 14.sp)
                TerminalField(runtimeUrl, onRuntimeUrl, "https://…-8000.app.github.dev", singleLine = true, capitalization = KeyboardCapitalization.None, keyboardType = KeyboardType.Uri)
                Text("Runtime token", color = Grey, fontSize = 14.sp)
                TerminalField(
                    runtimeToken, onRuntimeToken, "Token from the running Studio", singleLine = true,
                    visualTransformation = if (showToken) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingAction = if (runtimeToken.isBlank()) null else if (showToken) "HIDE" else "SHOW",
                    onTrailingAction = onToggleToken, capitalization = KeyboardCapitalization.None
                )
                PrimaryButton(if (runtimeConnected) "RECONNECT CHAT" else "CONNECT CHAT", onConnectRuntime, enabled = !busy && runtimeUrl.isNotBlank() && runtimeToken.isNotBlank())
                if (runtimeConnected) QuietButton("DISCONNECT CHAT", onDisconnectRuntime)
            }
            Spacer(Modifier.height(20.dp))
        }
    }
}

@Composable
private fun TerminalField(
    value: String, onValueChange: (String) -> Unit, placeholder: String,
    modifier: Modifier = Modifier, singleLine: Boolean = true, enabled: Boolean = true, large: Boolean = true,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    trailingAction: String? = null, onTrailingAction: (() -> Unit)? = null,
    capitalization: KeyboardCapitalization = KeyboardCapitalization.Sentences,
    keyboardType: KeyboardType = KeyboardType.Text
) {
    Row(
        modifier.fillMaxWidth().background(Surface, RoundedCornerShape(6.dp)).padding(horizontal = 14.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        BasicTextField(
            value = value, onValueChange = onValueChange, enabled = enabled, singleLine = singleLine,
            textStyle = TextStyle(color = White, fontFamily = Mono, fontSize = if (large) 16.sp else 14.sp, lineHeight = if (large) 24.sp else 19.sp),
            cursorBrush = SolidColor(Green),
            visualTransformation = visualTransformation,
            keyboardOptions = KeyboardOptions(capitalization = capitalization, keyboardType = keyboardType),
            modifier = Modifier.weight(1f).defaultMinSize(minHeight = if (large) 26.dp else 22.dp),
            decorationBox = { inner ->
                Box {
                    if (value.isEmpty() && placeholder.isNotEmpty()) Text(placeholder, color = Grey, fontFamily = Mono, fontSize = if (large) 16.sp else 14.sp)
                    inner()
                }
            }
        )
        if (!trailingAction.isNullOrBlank() && onTrailingAction != null) {
            Spacer(Modifier.width(8.dp))
            Text(trailingAction, color = Green, fontSize = 13.sp, fontWeight = FontWeight.Bold, modifier = Modifier.clickable { onTrailingAction() }.padding(4.dp))
        }
    }
}

@Composable
private fun PrimaryButton(
    label: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier
) {
    Button(
        onClick = onClick, enabled = enabled, modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(6.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Green, contentColor = Black,
            disabledContainerColor = SurfaceRaised, disabledContentColor = Grey
        ),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 15.dp)
    ) {
        Text(label, fontFamily = Mono, fontSize = 14.sp, fontWeight = FontWeight.Bold, letterSpacing = .4.sp)
    }
}

@Composable
private fun QuietButton(label: String, onClick: () -> Unit) {
    Text(
        label, color = Green, fontSize = 13.sp, fontFamily = Mono, fontWeight = FontWeight.Bold,
        modifier = Modifier.clickable { onClick() }.padding(horizontal = 7.dp, vertical = 10.dp)
    )
}

private fun openExternal(context: Context, url: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    } catch (_: Exception) { }
}
private fun statusColor(status: String) = when (status.lowercase()) {
    "success", "passed", "completed" -> Green
    "failure", "failed", "cancelled", "timed out" -> Red
    else -> Grey
}
