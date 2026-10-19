package com.omnitrix.mobile

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.ClickableText
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.material3.LocalTextStyle
import androidx.core.content.FileProvider
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextDecoration
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
import org.json.JSONTokener
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Base64
import java.util.UUID
import android.text.method.LinkMovementMethod
import android.view.ViewGroup
import android.widget.TextView
import androidx.compose.ui.viewinterop.AndroidView
import io.noties.markwon.Markwon
import io.noties.markwon.ext.latex.JLatexMathPlugin
import io.noties.markwon.ext.strikethrough.StrikethroughPlugin
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.tasklist.TaskListPlugin
import io.noties.markwon.html.HtmlPlugin
import io.noties.markwon.inlineparser.MarkwonInlineParserPlugin

private val Black = Color(0xFF080A07)
private val Surface = Color(0xFF11150E)
private val SurfaceRaised = Color(0xFF1B2115)
private val Green = Color(0xFFD0FF55)
private val White = Color(0xFFF0F2E8)
private val Grey = Color(0xFFA4AD98)
private val Red = Color(0xFFFF6B6B)
private val Mono = FontFamily.Monospace
private val Pixel = FontFamily(Font(R.font.pixelify_sans, weight = FontWeight.Normal))
private const val REPOSITORY = "som76377-alt/omnimatrix"
private const val HOSTED_BACKEND_DISCOVERY_URL =
    "https://raw.githubusercontent.com/som76377-alt/omnimatrix/main/config/mobile-backend.json"

private enum class AppTab(val title: String) {
    CHAT("Chat"), REPO("Repo"), STATUS("Runs"), ACCOUNT("Account")
}
private data class ChatMessage(
    val role: String,
    val text: String,
    val modelLabel: String? = null,
    val activityLines: List<String> = emptyList()
)

internal object ModelActivityLabelFormatter {
    private fun roleName(role: String): String = when (role.lowercase()) {
        "intent_engineer" -> "INTENT ENGINEER"
        "reasoning" -> "REASONING"
        "subject_solver" -> "SUBJECT SOLVER"
        "computation" -> "COMPUTATION"
        "coding" -> "CODING"
        "research" -> "RESEARCH"
        "critic" -> "CRITIC"
        "default" -> "OMNITRIX CORE"
        else -> role.replace('_', ' ').uppercase().ifBlank { "OMNITRIX CORE" }
    }

    private fun stepName(role: String, stage: String, completed: Boolean): String {
        val verb = when (stage) {
            "intent_engineer" -> if (completed) "task understood" else "clarifying the request"
            "critic" -> if (completed) "review finished" else "checking the draft for errors"
            "primary_inference" -> when (role) {
                "subject_solver" -> "solving the subject problem"
                "reasoning" -> "working through the reasoning"
                "computation" -> "checking the calculation"
                "coding" -> "working through the implementation"
                "research" -> "evaluating research evidence"
                else -> "working on the answer"
            }
            "tool_call_decision" -> if (completed) "tool decision complete" else "checking whether a permitted tool is needed"
            "answer_generation" -> if (completed) "response generated" else "generating a response"
            else -> if (completed) "stage complete" else "working"
        }
        return "${roleName(role)} · $verb"
    }

    private fun sourceLabel(identitySource: String): String = when (identitySource) {
        "provider_response" -> "provider-reported ID"
        "configured_id_pending_provider_response" -> "configured route; response ID pending"
        "configured_fallback" -> "configured fallback; provider omitted ID"
        "adapter_metadata" -> "adapter metadata; not provider-confirmed"
        else -> "identity not confirmed"
    }

    private fun modelLabel(record: JSONObject): String {
        val identitySource = record.optString("identity_source")
        val selectedModel = if (identitySource == "provider_response") {
            record.optString("model")
        } else {
            record.optString("configured_model")
        }
        val model = selectedModel.ifBlank { "model ID unavailable" }
        val provider = record.optString("provider").ifBlank { "provider unknown" }
        return "$provider · $model · ${sourceLabel(identitySource)}"
    }

    fun fromInFlight(activity: JSONObject?): String {
        if (activity == null) return "ROUTING · SELECTING SPECIALIST"
        val status = activity.optString("status")
        val role = activity.optString("role")
        val stage = activity.optString("stage")
        val prefix = if (status == "response_received") "STEP COMPLETE" else "WORKING"
        return "$prefix · ${stepName(role, stage, status == "response_received")} · ${modelLabel(activity)}"
    }

    fun progressLines(payload: JSONObject): List<String> {
        val output = linkedSetOf<String>()
        val history = payload.optJSONArray("activity_history")
        if (history != null) {
            for (index in 0 until history.length()) {
                val record = history.optJSONObject(index) ?: continue
                output.add("✓ ${stepName(record.optString("role"), record.optString("stage"), true)} · ${modelLabel(record)}")
            }
        }
        val current = payload.optJSONObject("activity")
        if (current != null && current.optString("status") == "request_in_flight") {
            output.add("● ${stepName(current.optString("role"), current.optString("stage"), false)} · ${modelLabel(current)}")
        }
        if (output.isEmpty() && payload.optBoolean("active")) {
            val plan = payload.optJSONObject("plan")
            val role = plan?.optString("primary_agent_role").orEmpty()
            if (role.isNotBlank() && role != "null") {
                output.add("● ${roleName(role)} · preparing its model request")
            } else {
                output.add("● OMNITRIX CORE · selecting the specialist")
            }
        }
        return output.toList().takeLast(6)
    }

    fun linesFromTrace(trace: JSONObject?): List<String> {
        val records = trace?.optJSONArray("activity") ?: return emptyList()
        val output = mutableListOf<String>()
        for (index in 0 until records.length()) {
            val record = records.optJSONObject(index) ?: continue
            output.add("✓ ${stepName(record.optString("role"), record.optString("stage"), true)} · ${modelLabel(record)}")
        }
        return output.takeLast(6)
    }

    fun fromTrace(trace: JSONObject?): String {
        val records = trace?.optJSONArray("activity")
            ?: return "MODEL ID UNAVAILABLE · no execution trace returned"
        var selected: JSONObject? = null
        for (index in records.length() - 1 downTo 0) {
            val record = records.optJSONObject(index) ?: continue
            if (selected == null) selected = record
            if (record.optString("stage") == "answer_generation") {
                selected = record
                break
            }
        }
        val record = selected ?: return "MODEL ID UNAVAILABLE · no model call recorded"
        val identitySource = record.optString("identity_source")
        val reportedModel = if (identitySource == "provider_response") {
            record.optString("model")
        } else {
            record.optString("configured_model")
        }
        val model = reportedModel.ifBlank { "model ID missing" }
        val provider = record.optString("provider").ifBlank { "provider unknown" }
        val role = record.optString("role").ifBlank { "role unknown" }
        val provenance = when (identitySource) {
            "provider_response" -> "provider-reported"
            "configured_fallback" -> "configured fallback; provider omitted ID"
            "adapter_metadata" -> "adapter metadata; not provider-confirmed"
            else -> "identity not confirmed"
        }
        val effort = record.optString("reasoning_effort_requested")
            .takeIf { it.isNotBlank() && it != "null" }
            ?.let { "$it effort requested" }
        val specialist = roleName(role)
        return listOf("ANSWER MODEL", specialist, provider, model, provenance, effort)
            .filter { !it.isNullOrBlank() && it != "null" }
            .joinToString(" · ")
    }
}
private data class RepoEntry(val name: String, val path: String, val type: String, val size: Long, val sha: String)
private data class CiRun(val title: String, val status: String, val branch: String, val url: String, val updated: String)
private data class GitHubRepository(
    val fullName: String,
    val name: String,
    val description: String,
    val isPrivate: Boolean,
    val defaultBranch: String,
    val updatedAt: String
)
private data class AppUpdate(
    val versionCode: Int,
    val versionName: String,
    val title: String,
    val notes: String,
    val downloadUrl: String,
    val sha256: String,
    val sizeBytes: Long
)
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
        window.statusBarColor = android.graphics.Color.rgb(8, 10, 7)
        window.navigationBarColor = android.graphics.Color.rgb(8, 10, 7)
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
        return true
    }

    fun isSafeRepositoryFullName(fullName: String): Boolean {
        val parts = fullName.split("/")
        if (parts.size != 2) return false
        return parts.all { part ->
            part.isNotBlank() && part != "." && part != ".." &&
                part.matches(Regex("[A-Za-z0-9_.-]+"))
        }
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
    private var refreshToken: String = prefs.getString("refresh_token", "") ?: ""
    private var accessTokenExpiresAt: Long = prefs.getLong("access_token_expires_at", 0L)
    private var refreshTokenExpiresAt: Long = prefs.getLong("refresh_token_expires_at", 0L)
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
        refreshToken = ""
        accessTokenExpiresAt = 0L
        refreshTokenExpiresAt = 0L
        prefs.edit()
            .remove("access_token").remove("refresh_token")
            .remove("access_token_expires_at").remove("refresh_token_expires_at")
            .remove("username").apply()
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
                    val expiresIn = result.optLong("expires_in", 0L)
                    val refreshExpiresIn = result.optLong("refresh_token_expires_in", 0L)
                    withContext(Dispatchers.IO) {
                        accessToken = value
                        refreshToken = result.optString("refresh_token", "")
                        accessTokenExpiresAt = if (expiresIn > 0L) System.currentTimeMillis() + expiresIn * 1000L else Long.MAX_VALUE
                        refreshTokenExpiresAt = if (refreshExpiresIn > 0L) System.currentTimeMillis() + refreshExpiresIn * 1000L else Long.MAX_VALUE
                        prefs.edit()
                            .putString("access_token", accessToken)
                            .putString("refresh_token", refreshToken)
                            .putLong("access_token_expires_at", accessTokenExpiresAt)
                            .putLong("refresh_token_expires_at", refreshTokenExpiresAt)
                            .apply()
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

    suspend fun listRepositories(accountHint: String): List<GitHubRepository> {
        val account = accountHint.trim().ifBlank { REPOSITORY.substringBefore("/") }
        val address = if (ready()) {
            "https://api.github.com/user/repos?visibility=all&affiliation=owner&sort=updated&per_page=100"
        } else {
            if (!account.matches(Regex("[A-Za-z0-9-]+"))) {
                throw IOException("The GitHub username is not valid.")
            }
            "https://api.github.com/users/" + encodePathPart(account) +
                "/repos?type=owner&sort=updated&per_page=100"
        }
        if (ready()) ensureValidAccessToken()
        val parsed = withContext(Dispatchers.IO) {
            JSONTokener(requestRaw("GET", address, null, accessToken.takeIf { ready() })).nextValue()
        }
        val items = parsed as? JSONArray ?: JSONArray()
        return buildList {
            for (index in 0 until items.length()) {
                val item = items.optJSONObject(index) ?: continue
                val fullName = item.optString("full_name", "")
                if (!GitHubInputValidation.isSafeRepositoryFullName(fullName)) continue
                add(
                    GitHubRepository(
                        fullName = fullName,
                        name = item.optString("name", fullName.substringAfter("/")),
                        description = item.optString("description", "").takeUnless { it == "null" }.orEmpty(),
                        isPrivate = item.optBoolean("private", false),
                        defaultBranch = item.optString("default_branch", "main").ifBlank { "main" },
                        updatedAt = item.optString("updated_at", "")
                    )
                )
            }
        }.sortedWith(compareBy<GitHubRepository> { it.isPrivate }.thenBy { it.name.lowercase() })
    }

    suspend fun listContents(repository: GitHubRepository, path: String): List<RepoEntry> {
        if (!GitHubInputValidation.isSafeRepositoryFullName(repository.fullName)) {
            throw IOException("That GitHub repository name is not valid.")
        }
        if (path.isNotBlank() && !GitHubInputValidation.isSafeRepoPath(path)) {
            throw IOException("That repository path is not available in the app.")
        }
        val encoded = if (path.isBlank()) "" else path.split("/").joinToString("/") { encodePathPart(it) }
        val encodedRepo = repository.fullName.split("/").joinToString("/") { encodePathPart(it) }
        val address = "https://api.github.com/repos/" + encodedRepo + "/contents" +
            (if (encoded.isBlank()) "" else "/$encoded") +
            "?ref=" + encodePathPart(repository.defaultBranch)
        if (ready()) ensureValidAccessToken()
        val parsed = withContext(Dispatchers.IO) {
            JSONTokener(requestRaw("GET", address, null, accessToken.takeIf { ready() })).nextValue()
        }
        val entriesJson = when (parsed) {
            is JSONArray -> parsed
            is JSONObject -> JSONArray().put(parsed)
            else -> JSONArray()
        }
        return buildList {
            for (i in 0 until entriesJson.length()) {
                val item = entriesJson.optJSONObject(i) ?: continue
                val itemPath = item.optString("path", "")
                val name = item.optString("name", "")
                val type = item.optString("type", "")
                if (name.isBlank() || name.startsWith(".") ||
                    !GitHubInputValidation.isSafeRepoPath(itemPath)) continue
                add(RepoEntry(name, itemPath, type, item.optLong("size"), item.optString("sha", "")))
            }
        }.sortedWith(compareBy<RepoEntry> { if (it.type == "dir") 0 else 1 }.thenBy { it.name.lowercase() })
    }

    suspend fun readFile(repository: GitHubRepository, path: String): Pair<String, String> {
        if (!GitHubInputValidation.isSafeRepositoryFullName(repository.fullName) ||
            !GitHubInputValidation.isSafeRepoPath(path)) {
            throw IOException("That repository path is not available in the app.")
        }
        val encodedPath = path.split("/").joinToString("/") { encodePathPart(it) }
        val encodedRepo = repository.fullName.split("/").joinToString("/") { encodePathPart(it) }
        val json = getJson(
            "https://api.github.com/repos/" + encodedRepo + "/contents/" + encodedPath +
                "?ref=" + encodePathPart(repository.defaultBranch)
        )
        if (json.optString("type") != "file") throw IOException("Choose a text file.")
        if (json.optLong("size") > 65536) throw IOException("This file is larger than the mobile editor's 64 KB limit.")
        val raw = json.optString("content", "")
        if (raw.isBlank()) throw IOException("GitHub did not return file contents.")
        val bytes = try { Base64.getMimeDecoder().decode(raw) } catch (_: Exception) { throw IOException("This file is not readable as UTF-8 text.") }
        val text = try { String(bytes, StandardCharsets.UTF_8) } catch (_: Exception) { throw IOException("This file is not UTF-8 text.") }
        if (text.contains('\u0000')) throw IOException("Binary files cannot be edited here.")
        return text to json.optString("sha", "")
    }

    suspend fun updateFile(repository: GitHubRepository, path: String, content: String, sha: String): String {
        if (repository.fullName != REPOSITORY) {
            throw IOException("Edits are currently restricted to the Omnitrix repository. Other repositories are read-only here.")
        }
        if (!GitHubInputValidation.isSafeRepositoryFullName(repository.fullName) ||
            !GitHubInputValidation.isSafeRepoPath(path)) {
            throw IOException("That repository path is not writable from the app.")
        }
        if (content.toByteArray(StandardCharsets.UTF_8).size > 65536) throw IOException("Keep mobile edits under 64 KB.")
        if (sha.isBlank()) throw IOException("No original file SHA is available. Reload before saving.")
        val encodedPath = path.split("/").joinToString("/") { encodePathPart(it) }
        val encodedRepo = repository.fullName.split("/").joinToString("/") { encodePathPart(it) }
        val jsonBody = JSONObject()
            .put("message", "Edit " + path + " from Omnitrix Android")
            .put("content", Base64.getEncoder().encodeToString(content.toByteArray(StandardCharsets.UTF_8)))
            .put("sha", sha)
            .put("branch", repository.defaultBranch)
        val result = requestJson("PUT", "/repos/" + encodedRepo + "/contents/" + encodedPath, jsonBody)
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

    private suspend fun getJson(path: String): JSONObject {
        if (ready()) return requestJson("GET", path, null)
        return withContext(Dispatchers.IO) {
            val full = if (path.startsWith("https://")) path else "https://api.github.com" + path
            JSONObject(requestRaw("GET", full, null))
        }
    }

    private suspend fun requestJson(method: String, path: String, body: JSONObject?): JSONObject {
        if (!ready()) throw IOException("Sign in with GitHub first.")
        ensureValidAccessToken()
        return withContext(Dispatchers.IO) {
            val full = if (path.startsWith("https://")) path else "https://api.github.com" + path
            val content = body?.toString()
            JSONObject(requestRaw(method, full, content, accessToken, "application/json; charset=utf-8", "application/vnd.github+json"))
        }
    }

    private suspend fun ensureValidAccessToken() {
        if (!ready()) throw IOException("Sign in with GitHub first.")
        if (accessTokenExpiresAt == 0L || System.currentTimeMillis() < accessTokenExpiresAt - 60_000L) return
        if (refreshToken.isBlank() || System.currentTimeMillis() >= refreshTokenExpiresAt) {
            throw IOException("GitHub sign-in expired. Sign in again from Account.")
        }
        val body = form(mapOf(
            "client_id" to clientId,
            "grant_type" to "refresh_token",
            "refresh_token" to refreshToken
        ))
        val result = withContext(Dispatchers.IO) {
            JSONObject(requestRaw(
                "POST", "https://github.com/login/oauth/access_token", body,
                contentType = "application/x-www-form-urlencoded; charset=utf-8", accept = "application/json"
            ))
        }
        if (result.has("error")) {
            signOut()
            throw IOException("GitHub session expired. Sign in again from Account.")
        }
        val newAccess = result.optString("access_token", "")
        if (newAccess.isBlank()) throw IOException("GitHub did not refresh the session.")
        val newRefresh = result.optString("refresh_token", "").ifBlank { refreshToken }
        val accessLifetime = result.optLong("expires_in", 0L)
        val refreshLifetime = result.optLong("refresh_token_expires_in", 0L)
        accessToken = newAccess
        refreshToken = newRefresh
        accessTokenExpiresAt = if (accessLifetime > 0L) System.currentTimeMillis() + accessLifetime * 1000L else Long.MAX_VALUE
        refreshTokenExpiresAt = if (refreshLifetime > 0L) System.currentTimeMillis() + refreshLifetime * 1000L else refreshTokenExpiresAt
        prefs.edit()
            .putString("access_token", accessToken)
            .putString("refresh_token", refreshToken)
            .putLong("access_token_expires_at", accessTokenExpiresAt)
            .putLong("refresh_token_expires_at", refreshTokenExpiresAt)
            .apply()
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
    private var hostedBase: String = ""
    private var useHostedBackend: Boolean = true

    fun configure(urlValue: String, tokenValue: String) {
        base = RuntimeInputValidation.normalizeStudioUrl(urlValue)
        token = RuntimeInputValidation.validateRuntimeToken(tokenValue)
        useHostedBackend = false
        prefs.edit().putString("url", base).putString("token", token).apply()
    }
    fun ready() = base.isNotBlank() && token.isNotBlank()
    fun disconnect() {
        token = ""
        useHostedBackend = true
        prefs.edit().remove("token").apply()
    }
    suspend fun get(route: String) = requestPrivate("GET", route, null)
    suspend fun post(route: String, body: JSONObject) = requestPrivate("POST", route, body)

    suspend fun connectAutomatically(): JSONObject {
        // Perform one real readiness request at connection time instead of showing
        // the app as connected after only downloading a static manifest.
        useHostedBackend = true
        return hostedHealth().put("connection_mode", "health-checked")
    }

    suspend fun hostedHealth(): JSONObject {
        val address = discoverHostedBase() + "/api/mobile/health"
        val health = requestPublic("GET", address, null)
        if (!health.optBoolean("chat_available")) {
            val reason = health.optString("reason")
            val message = when (reason) {
                "provider_key_missing" -> "Hosted AI is waiting for its server-side model key."
                "model_not_configured" -> "Hosted AI model configuration is incomplete."
                "public_chat_disabled" -> "Hosted chat is disabled on the server."
                else -> "Hosted AI is not ready."
            }
            throw IOException(message)
        }
        return health
    }

    suspend fun sendChat(body: JSONObject): JSONObject {
        if (!useHostedBackend && ready()) {
            return requestPrivate("POST", "/api/chat", body)
        }
        useHostedBackend = true
        return requestPublic("POST", discoverHostedBase() + "/api/mobile/chat", body)
    }

    suspend fun activity(sessionId: String): JSONObject {
        if (!useHostedBackend && ready()) {
            val health = requestPrivate("GET", "/api/health", null)
            val current = health.optJSONObject("active_execution")
            return JSONObject()
                .put("ok", true)
                .put("active", current != null)
                .put("activity", current)
        }
        val encodedSession = URLEncoder.encode(sessionId, StandardCharsets.UTF_8.name())
        return requestPublic(
            "GET",
            discoverHostedBase() + "/api/mobile/activity?session_id=" + encodedSession,
            null
        )
    }

    private suspend fun discoverHostedBase(): String {
        if (hostedBase.isNotBlank()) return hostedBase
        val manifest = requestPublic("GET", HOSTED_BACKEND_DISCOVERY_URL, null)
        if (!manifest.optBoolean("chat_enabled")) {
            throw IOException("Hosted chat is not deployed yet.")
        }
        val candidate = manifest.optString("base_url", "").trimEnd('/')
        if (candidate.isBlank()) throw IOException("Hosted chat server URL is not configured.")
        val parsed = try { URL(candidate) } catch (_: Exception) {
            throw IOException("Hosted chat server URL is invalid.")
        }
        val host = parsed.host.lowercase()
        if (parsed.protocol != "https" ||
            !(host.endsWith(".onrender.com") || host == "onrender.com") ||
            parsed.path.isNotEmpty() || parsed.query != null || parsed.ref != null ||
            candidate.contains("@")
        ) {
            throw IOException("Hosted chat server URL failed its HTTPS host validation.")
        }
        hostedBase = candidate
        return hostedBase
    }

    private suspend fun requestPrivate(
        method: String, route: String, body: JSONObject?
    ): JSONObject = withContext(Dispatchers.IO) {
        if (!ready()) throw IOException("No saved private runtime connection.")
        val connection = URL(base + route).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 12000
        connection.readTimeout = if (route == "/api/tests/run") 210000 else 25000
        connection.useCaches = false
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty(
            "Authorization",
            "Bearer " + RuntimeInputValidation.validateRuntimeToken(token)
        )
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        try {
            if (body != null) connection.outputStream.use {
                it.write(body.toString().toByteArray(StandardCharsets.UTF_8))
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
            val contentType = connection.contentType.orEmpty()
            val looksLikeHtml = text.trimStart().startsWith("<!doctype html", ignoreCase = true) ||
                text.trimStart().startsWith("<html", ignoreCase = true) ||
                contentType.contains("text/html", ignoreCase = true)
            if (looksLikeHtml) {
                throw IOException("The runtime returned an HTML sign-in page instead of its API.")
            }
            if (code !in 200..299) {
                val detail = try { JSONObject(text).optString("error", "") } catch (_: Exception) { "" }
                throw IOException(if (detail.isBlank()) "Runtime returned HTTP " + code else detail)
            }
            try {
                JSONObject(text)
            } catch (_: Exception) {
                throw IOException(
                    "Runtime returned invalid JSON (HTTP " + code +
                        ", content type " + contentType.ifBlank { "unknown" } + ")."
                )
            }
        } finally { connection.disconnect() }
    }

    private suspend fun requestPublic(
        method: String, address: String, body: JSONObject?
    ): JSONObject = withContext(Dispatchers.IO) {
        val connection = URL(address).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 20000
        connection.readTimeout = if (address.contains("onrender.com")) 120000 else 20000
        connection.useCaches = false
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("User-Agent", "Omnitrix-Android")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        try {
            if (body != null) connection.outputStream.use {
                it.write(body.toString().toByteArray(StandardCharsets.UTF_8))
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
            val contentType = connection.contentType.orEmpty()
            val looksLikeHtml = text.trimStart().startsWith("<!doctype html", ignoreCase = true) ||
                text.trimStart().startsWith("<html", ignoreCase = true) ||
                contentType.contains("text/html", ignoreCase = true)
            if (looksLikeHtml) {
                throw IOException("Hosted chat returned a web page instead of its API.")
            }
            if (code !in 200..299) {
                val detail = try { JSONObject(text).optString("error", "") } catch (_: Exception) { "" }
                throw IOException(if (detail.isBlank()) "Hosted chat returned HTTP " + code else detail)
            }
            try {
                JSONObject(text)
            } catch (_: Exception) {
                throw IOException("Hosted chat returned invalid JSON.")
            }
        } finally { connection.disconnect() }
    }
}


private object AppUpdater {
    suspend fun checkForUpdate(): AppUpdate? = withContext(Dispatchers.IO) {
        val connection = URL("https://api.github.com/repos/" + REPOSITORY + "/releases/latest")
            .openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.connectTimeout = 12000
        connection.readTimeout = 18000
        connection.useCaches = false
        connection.setRequestProperty("Accept", "application/vnd.github+json")
        connection.setRequestProperty("User-Agent", "Omnitrix-Android-Updater")
        connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
        try {
            val code = connection.responseCode
            if (code !in 200..299) throw IOException("Update check returned HTTP " + code + ".")
            val body = connection.inputStream.bufferedReader(StandardCharsets.UTF_8).use { it.readText() }
            val release = JSONObject(body)
            val tag = release.optString("tag_name", "")
            val version = Regex("""omnitrix-android-build-(\d+)-attempt-\d+""")
                .matchEntire(tag)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: return@withContext null
            if (version <= BuildConfig.VERSION_CODE) return@withContext null
            val assets = release.optJSONArray("assets") ?: JSONArray()
            var apk: JSONObject? = null
            for (index in 0 until assets.length()) {
                val candidate = assets.optJSONObject(index) ?: continue
                if (candidate.optString("name") == "Omnitrix.apk") {
                    apk = candidate
                    break
                }
            }
            val asset = apk ?: throw IOException("The newest Omnitrix release has no APK asset.")
            val digest = asset.optString("digest", "").removePrefix("sha256:").lowercase()
            if (!digest.matches(Regex("[0-9a-f]{64}"))) {
                throw IOException("The newest APK release has no valid SHA-256 checksum.")
            }
            val downloadUrl = asset.optString("browser_download_url", "")
            if (!downloadUrl.startsWith("https://github.com/" + REPOSITORY + "/releases/")) {
                throw IOException("The update download URL failed validation.")
            }
            AppUpdate(
                versionCode = version,
                versionName = release.optString("name", "Build " + version),
                title = release.optString("name", "Omnitrix build " + version),
                notes = release.optString("body", ""),
                downloadUrl = downloadUrl,
                sha256 = digest,
                sizeBytes = asset.optLong("size", 0L)
            )
        } finally {
            connection.disconnect()
        }
    }

    suspend fun download(context: Context, update: AppUpdate, onProgress: (Int) -> Unit): File =
        withContext(Dispatchers.IO) {
            if (update.sizeBytes <= 0L || update.sizeBytes > 50L * 1024L * 1024L) {
                throw IOException("The APK file size is not within the allowed limit.")
            }
            val directory = File(context.filesDir, "updates")
            if (!directory.exists() && !directory.mkdirs()) throw IOException("Could not create the update folder.")
            val target = File(directory, "Omnitrix-" + update.versionCode + ".apk")
            if (target.isFile && verifySha256(target, update.sha256)) {
                onProgress(100)
                return@withContext target
            }
            val temporary = File(directory, "Omnitrix-" + update.versionCode + ".apk.part")
            val connection = URL(update.downloadUrl).openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 20000
            connection.readTimeout = 120000
            connection.useCaches = false
            connection.setRequestProperty("User-Agent", "Omnitrix-Android-Updater")
            connection.setRequestProperty("Accept", "application/vnd.android.package-archive")
            try {
                val code = connection.responseCode
                if (code !in 200..299) throw IOException("APK download returned HTTP " + code + ".")
                val actualLength = connection.contentLengthLong
                if (actualLength > 0L && actualLength > 50L * 1024L * 1024L) {
                    throw IOException("The APK download is larger than 50 MB.")
                }
                var total = 0L
                connection.inputStream.use { input ->
                    FileOutputStream(temporary).use { output ->
                        val buffer = ByteArray(16 * 1024)
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            output.write(buffer, 0, count)
                            total += count
                            val denominator = if (actualLength > 0L) actualLength else update.sizeBytes
                            onProgress(((total * 100L) / denominator.coerceAtLeast(1L)).toInt().coerceIn(0, 99))
                            if (total > 50L * 1024L * 1024L) throw IOException("The APK download exceeded the size limit.")
                        }
                        output.fd.sync()
                    }
                }
                if (total != update.sizeBytes) throw IOException("The downloaded APK size did not match the release.")
                if (!verifySha256(temporary, update.sha256)) throw IOException("The downloaded APK failed its SHA-256 integrity check.")
                if (target.exists() && !target.delete()) throw IOException("Could not replace the cached update.")
                if (!temporary.renameTo(target)) throw IOException("Could not finalize the downloaded update.")
                onProgress(100)
                target
            } catch (e: Exception) {
                temporary.delete()
                throw e
            } finally {
                connection.disconnect()
            }
        }

    private fun verifySha256(file: File, expected: String): Boolean {
        if (!file.isFile || expected.isBlank()) return false
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(16 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        val actual = digest.digest().joinToString("") { byte -> "%02x".format(byte) }
        return actual.equals(expected, ignoreCase = true)
    }

    fun launchInstaller(context: Context, apkFile: File) {
        if (!apkFile.isFile) throw IOException("The downloaded update file is missing.")
        val uri = FileProvider.getUriForFile(context, context.packageName + ".fileprovider", apkFile)
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
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
    var runtimeMessage by remember { mutableStateOf("") }
    var chatBusy by remember { mutableStateOf(false) }
    var chatInput by remember { mutableStateOf("") }
    var messages by remember { mutableStateOf(emptyList<ChatMessage>()) }
    var modelActivityLabel by remember { mutableStateOf("CONNECTING · checking hosted AI") }
    var modelActivityLines by remember { mutableStateOf(emptyList<String>()) }
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
    var repositories by remember { mutableStateOf<List<GitHubRepository>>(emptyList()) }
    var selectedRepository by remember { mutableStateOf<GitHubRepository?>(null) }
    var availableUpdate by remember { mutableStateOf<AppUpdate?>(null) }
    var showUpdateDialog by remember { mutableStateOf(false) }
    var updateDownloadedPath by remember { mutableStateOf<String?>(null) }
    var updateDownloadBusy by remember { mutableStateOf(false) }
    var updateProgress by remember { mutableStateOf(0) }
    var updateMessage by remember { mutableStateOf("") }

    fun startUpdateDownload(update: AppUpdate) {
        if (updateDownloadBusy) return
        scope.launch {
            updateDownloadBusy = true
            updateProgress = 0
            updateMessage = "Downloading and verifying the update…"
            try {
                val file = AppUpdater.download(context, update) { progress -> updateProgress = progress }
                updateDownloadedPath = file.absolutePath
                updateMessage = "Update downloaded and verified. Tap INSTALL UPDATE to continue."
            } catch (e: Exception) {
                updateMessage = e.message ?: "Could not download the update."
                updateDownloadedPath = null
            } finally {
                updateDownloadBusy = false
            }
        }
    }

    fun installDownloadedUpdate() {
        val path = updateDownloadedPath
        if (path.isNullOrBlank() || !File(path).isFile) {
            availableUpdate?.let { startUpdateDownload(it) }
            return
        }
        if (Build.VERSION.SDK_INT >= 26 && !context.packageManager.canRequestPackageInstalls()) {
            updateMessage = "Allow installs for Omnitrix in Android Settings, then return and tap INSTALL UPDATE again."
            try {
                context.startActivity(
                    Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.packageName))
                )
            } catch (e: Exception) {
                updateMessage = e.message ?: "Could not open Android's install-permission settings."
            }
            return
        }
        try {
            AppUpdater.launchInstaller(context, File(path))
        } catch (e: Exception) {
            updateMessage = e.message ?: "Could not open Android's installer."
        }
    }

    fun loadRepositories() {
        scope.launch {
            repoBusy = true
            repoMessage = ""
            try {
                val account = username.ifBlank { REPOSITORY.substringBefore("/") }
                repositories = github.listRepositories(account)
                selectedRepository = null
                repoPath = ""
                entries = emptyList()
                selectedFile = null
                repoMessage = if (repositories.isEmpty()) "No public repositories were found for @$account." else ""
            } catch (e: Exception) {
                repoMessage = e.message ?: "Could not load repositories."
            } finally {
                repoBusy = false
            }
        }
    }

    fun loadRepo(path: String) {
        val repository = selectedRepository ?: return
        scope.launch {
            repoBusy = true
            repoMessage = ""
            selectedFile = null
            try {
                entries = github.listContents(repository, path)
                repoPath = path
                repoMessage = if (entries.isEmpty()) "No visible files here." else ""
            } catch (e: Exception) {
                repoMessage = e.message ?: "Could not load this folder."
            } finally { repoBusy = false }
        }
    }

    fun selectRepository(repository: GitHubRepository?) {
        selectedRepository = repository
        selectedFile = null
        fileDraft = ""
        fileOriginal = ""
        fileSha = ""
        repoPath = ""
        entries = emptyList()
        repoMessage = ""
        if (repository != null) loadRepo("")
    }

    fun openRepoEntry(entry: RepoEntry) {
        if (entry.type == "dir") {
            loadRepo(entry.path)
            return
        }
        val repository = selectedRepository ?: return
        scope.launch {
            repoBusy = true
            repoMessage = ""
            try {
                val result = github.readFile(repository, entry.path)
                selectedFile = entry
                fileDraft = result.first
                fileOriginal = result.first
                fileSha = result.second
            } catch (e: Exception) {
                repoMessage = e.message ?: "Could not open file."
            } finally { repoBusy = false }
        }
    }

    fun backRepo() {
        if (selectedFile != null) {
            selectedFile = null
            fileDraft = ""
            fileOriginal = ""
            fileSha = ""
            repoMessage = ""
        } else if (repoPath.isNotBlank()) {
            loadRepo(if (repoPath.contains("/")) repoPath.substringBeforeLast("/") else "")
        } else {
            selectRepository(null)
        }
    }

    fun saveRepoFile() {
        val entry = selectedFile ?: return
        val repository = selectedRepository ?: return
        if (repository.fullName != REPOSITORY) {
            repoMessage = "Edits are currently restricted to the Omnitrix repository."
            confirmCommit = false
            return
        }
        scope.launch {
            repoBusy = true
            repoMessage = ""
            try {
                github.updateFile(repository, entry.path, fileDraft, fileSha)
                fileOriginal = fileDraft
                val refreshed = github.readFile(repository, entry.path)
                fileSha = refreshed.second
                repoMessage = "Committed to main."
            } catch (e: Exception) {
                repoMessage = e.message ?: "Commit failed."
            } finally { repoBusy = false; confirmCommit = false }
        }
    }

    fun loadRuns() {
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
            runtimeMessage = ""
            try {
                runtime.configure(chatUrl, chatToken)
                val health = runtime.get("/api/health")
                if (health.optString("provider_mode") == "offline-demo") {
                    throw IOException("This server uses the offline demo model, not live AI.")
                }
                if (!health.optBoolean("gemini_key_detected")) {
                    throw IOException("This server has no live Gemini provider key configured.")
                }
                runtimeConnected = true
                runtimeMessage = ""
            } catch (e: Exception) {
                runtimeConnected = false
                runtimeMessage = e.message ?: "Runtime connection failed."
            } finally { chatBusy = false }
        }
    }

    fun connectHostedRuntime() {
        scope.launch {
            chatBusy = true
            runtimeMessage = ""
            modelActivityLabel = "CONNECTING · checking hosted AI"
            try {
                val readiness = runtime.connectAutomatically()
                runtimeConnected = true
                runtimeMessage = ""
                modelActivityLabel = when {
                    readiness.optBoolean("reasoning_specialist_available") ->
                        "READY · OpenRouter reasoning route available"
                    readiness.optBoolean("openrouter_key_detected") ->
                        "READY · OpenRouter key visible to backend, but reasoning route unavailable"
                    readiness.optString("reasoning_route_status") == "provider_key_missing" ->
                        "READY · Gemini route available; OpenRouter key not visible to the running backend"
                    else ->
                        "READY · primary route available; no separate OpenRouter reasoning route"
                }
            } catch (e: Exception) {
                runtimeConnected = false
                runtimeMessage = e.message ?: "Hosted chat is not available."
                modelActivityLabel = "CONNECTION FAILED · hosted AI not ready"
            } finally { chatBusy = false }
        }
    }

    LaunchedEffect(Unit) {
        if (githubConnected) username = github.username
        loadRuns()
        loadRepositories()
        connectHostedRuntime()
        if (BuildConfig.AUTO_UPDATES_ENABLED) {
            launch {
                try {
                    val update = AppUpdater.checkForUpdate()
                    if (update != null) {
                        availableUpdate = update
                        showUpdateDialog = true
                        startUpdateDownload(update)
                    }
                } catch (_: Exception) {
                    // Update checks are best-effort and never block chat startup.
                }
            }
        }
    }

    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Green, onPrimary = Black, secondary = Green, background = Black,
            surface = Surface, onSurface = White, error = Red
        ),
        typography = Typography()
    ) {
        CompositionLocalProvider(LocalTextStyle provides TextStyle(fontFamily = Mono, color = White)) {
            Scaffold(
            containerColor = Black,
            contentWindowInsets = WindowInsets.safeDrawing,
            bottomBar = {
                Row(
                    Modifier.fillMaxWidth().background(Black).navigationBarsPadding().padding(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(5.dp)
                ) {
                    AppTab.entries.forEach { destination ->
                        Column(
                            Modifier.weight(1f).background(if (tab == destination) SurfaceRaised else Black, RoundedCornerShape(2.dp))
                                .clickable { tab = destination }.padding(vertical = 13.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(destination.title, fontSize = 14.sp, color = if (tab == destination) Green else Grey, fontWeight = if (tab == destination) FontWeight.Bold else FontWeight.Medium, fontFamily = Pixel)
                        }
                    }
                }
            }
        ) { insets ->
            Box(Modifier.fillMaxSize().padding(insets).background(Black)) {
                when (tab) {
                    AppTab.CHAT -> ChatScreen(
                        messages, chatInput, runtimeConnected, chatBusy, runtimeMessage, modelActivityLabel, modelActivityLines,
                        { chatInput = it },
                        {
                            val prompt = chatInput.trim()
                            if (runtimeConnected && prompt.isNotEmpty() && !chatBusy) {
                                messages = messages + ChatMessage("YOU", prompt)
                                chatInput = ""
                                chatBusy = true
                                modelActivityLines = emptyList()
                                scope.launch {
                                    modelActivityLabel = "ROUTING · selecting the right specialist"
                                    val activityPoller = launch {
                                        while (true) {
                                            try {
                                                val status = runtime.activity(sessionId)
                                                if (status.optBoolean("active")) {
                                                    val lines = ModelActivityLabelFormatter.progressLines(status)
                                                    if (lines.isNotEmpty()) {
                                                        modelActivityLines = lines
                                                        modelActivityLabel = lines.last()
                                                    } else {
                                                        modelActivityLabel = "OMNITRIX · specialist plan selected"
                                                    }
                                                } else if (modelActivityLines.isEmpty()) {
                                                    modelActivityLabel = "OMNITRIX · preparing the specialist route"
                                                }
                                            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                                                throw cancelled
                                            } catch (_: Exception) {
                                                // Preserve the last trustworthy state when telemetry is briefly unavailable.
                                                if (modelActivityLines.isEmpty()) {
                                                    modelActivityLabel = "OMNITRIX · preparing the specialist route"
                                                }
                                            }
                                            delay(1000)
                                        }
                                    }
                                    try {
                                        val response = runtime.sendChat(
                                            JSONObject().put("message", prompt).put("session_id", sessionId)
                                        )
                                        val trace = response.optJSONObject("execution_trace")
                                        val modelLabel = ModelActivityLabelFormatter.fromTrace(trace)
                                        val completedLines = ModelActivityLabelFormatter.linesFromTrace(trace)
                                        messages = messages + ChatMessage(
                                            "OMNITRIX",
                                            response.optString("reply", "No response text returned."),
                                            modelLabel,
                                            completedLines
                                        )
                                        modelActivityLines = completedLines
                                        modelActivityLabel = modelLabel
                                    } catch (e: Exception) {
                                        val error = e.message ?: "This attempt failed."
                                        messages = messages + ChatMessage(
                                            "SYSTEM",
                                            "This attempt failed: $error\nYou can retry without reconnecting."
                                        )
                                        modelActivityLabel = "ATTEMPT FAILED · retry available"
                                    } finally {
                                        activityPoller.cancel()
                                        chatBusy = false
                                    }
                                }
                            }
                        },
                        { connectHostedRuntime() }
                    )
                    AppTab.REPO -> RepoScreen(
                        connected = githubConnected,
                        accountName = username.ifBlank { REPOSITORY.substringBefore("/") },
                        repositories = repositories,
                        selectedRepository = selectedRepository,
                        folder = repoPath,
                        entries = entries,
                        selected = selectedFile,
                        draft = fileDraft,
                        original = fileOriginal,
                        busy = repoBusy,
                        message = repoMessage,
                        onBack = { backRepo() },
                        onRefresh = {
                            if (selectedRepository == null) loadRepositories() else loadRepo(repoPath)
                        },
                        onOpen = { openRepoEntry(it) },
                        onDraft = { fileDraft = it },
                        onCommit = { confirmCommit = true },
                        onSignIn = { tab = AppTab.ACCOUNT },
                        onSelectRepository = { selectRepository(it) },
                        onNavigate = { loadRepo(it) }
                    )
                    AppTab.STATUS -> StatusScreen(
                        runs, runsBusy, runsMessage,
                        { loadRuns() },
                        { url -> openExternal(context, url) }
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
                                        try { runs = github.recentRuns(); runsMessage = "" }
                                        catch (loadError: Exception) { runsMessage = loadError.message ?: "Could not load workflows." }
                                        try {
                                            repositories = github.listRepositories(username)
                                            selectedRepository = null
                                            entries = emptyList()
                                            repoPath = ""
                                            repoMessage = ""
                                        } catch (loadError: Exception) {
                                            repoMessage = loadError.message ?: "Could not load repositories."
                                        }
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
                            runtime.disconnect()
                            runtimeConnected = false
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
                text = { Text("This writes the edited file directly to the public repository's main branch and creates a Git commit.", color = Grey, fontSize = 14.sp, lineHeight = 21.sp) },
                confirmButton = {
                    TextButton(onClick = { saveRepoFile() }) { Text("COMMIT FILE", color = Green, fontSize = 14.sp) }
                },
                dismissButton = {
                    TextButton(onClick = { confirmCommit = false }) { Text("CANCEL", color = White, fontSize = 14.sp) }
                }
            )
        }

        if (showUpdateDialog && availableUpdate != null) {
            val update = availableUpdate!!
            AlertDialog(
                onDismissRequest = { showUpdateDialog = false },
                containerColor = Surface,
                title = { Text("OMNITRIX UPDATE", color = Green, fontSize = 20.sp, fontWeight = FontWeight.Bold) },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(update.title, color = White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        Text("A verified update is available. Omnitrix downloads it automatically in the background.", color = Grey, fontSize = 13.sp, lineHeight = 19.sp)
                        if (updateDownloadBusy) {
                            Text("DOWNLOADING… $updateProgress%", color = Green, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                        }
                        if (updateMessage.isNotBlank()) {
                            Text(
                                updateMessage,
                                color = if (updateMessage.contains("failed", true) || updateMessage.contains("could not", true)) Red else Grey,
                                fontSize = 12.sp,
                                lineHeight = 17.sp
                            )
                        }
                        if (update.notes.isNotBlank()) {
                            Text(update.notes.trim().take(320), color = Grey, fontSize = 12.sp, lineHeight = 17.sp)
                        }
                    }
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            if (updateDownloadedPath != null) installDownloadedUpdate()
                            else if (!updateDownloadBusy) startUpdateDownload(update)
                        },
                        enabled = !updateDownloadBusy
                    ) {
                        Text(
                            if (updateDownloadedPath != null) "INSTALL UPDATE"
                            else if (updateDownloadBusy) "DOWNLOADING…"
                            else "RETRY DOWNLOAD",
                            color = Green,
                            fontSize = 13.sp
                        )
                    }
                },
                dismissButton = {
                    TextButton(onClick = { showUpdateDialog = false }) {
                        Text("LATER", color = White, fontSize = 13.sp)
                    }
                }
            )
        }

        }
    }
}

@Composable
private fun AppHeader(title: String, detail: String? = null, activityLabel: String? = null) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 22.dp).padding(top = 10.dp, bottom = 12.dp)) {
        Text("OMNITRIX", color = Green, fontSize = 12.sp, letterSpacing = 2.4.sp, fontWeight = FontWeight.Bold, fontFamily = Mono)
        if (!activityLabel.isNullOrBlank()) {
            Spacer(Modifier.height(3.dp))
            Text(
                activityLabel,
                color = if (activityLabel.startsWith("THINKING") || activityLabel.startsWith("MODEL RESPONSE")) Green else Grey,
                fontSize = 10.sp,
                lineHeight = 14.sp,
                fontFamily = Mono
            )
        }
        Spacer(Modifier.height(6.dp))
        Text(title, color = White, fontSize = 27.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold, fontFamily = Pixel)
        if (!detail.isNullOrBlank()) {
            Spacer(Modifier.height(3.dp))
            Text(detail, color = Grey, fontSize = 13.sp, lineHeight = 18.sp)
        }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().height(1.dp).background(Green.copy(alpha = 0.28f)))
    }
}



internal object MarkwonMathNormalizer {
    private val fencedCode = Regex("""(?ms)^ {0,3}(`{3,}|~{3,})[^\r\n]*\r?\n[\s\S]*?^ {0,3}\1[ \t]*(?:\r?\n|$)""")
    private val inlineCode = Regex("""(`+)[^\r\n]*?\1""")
    private val displayMath = Regex("""\\\[([\s\S]*?)\\\]""")
    private val inlineMath = Regex("""\\\((.+?)\\\)""")

    fun normalize(source: String): String {
        val protectedParts = mutableListOf<Pair<String, String>>()

        fun protect(value: String): String {
            val token = "\uE000OMNITRIX_PROTECTED${protectedParts.size}\uE001"
            val uniqueToken = token.replace("${protectedParts.size}", protectedParts.size.toString())
            protectedParts.add(uniqueToken to value)
            return uniqueToken
        }

        var result = fencedCode.replace(source) { protect(it.value) }
        result = inlineCode.replace(result) { protect(it.value) }

        result = displayMath.replace(result) { match ->
            "\n\n\$\$\n" + match.groupValues[1].trim('\r', '\n') + "\n\$\$\n\n"
        }
        result = inlineMath.replace(result) { match ->
            "\$\$" + match.groupValues[1] + "\$\$"
        }

        protectedParts.forEach { (token, original) ->
            result = result.replace(token, original)
        }
        return result
    }
}

@Composable
private fun MarkdownMessage(content: String) {
    val context = LocalContext.current
    val markwon = remember(context) {
        Markwon.builder(context)
            .usePlugin(StrikethroughPlugin.create())
            .usePlugin(TablePlugin.create(context))
            .usePlugin(TaskListPlugin.create(context))
            .usePlugin(MarkwonInlineParserPlugin.create())
            .usePlugin(JLatexMathPlugin.create(
                context.resources.displayMetrics.scaledDensity * 15f,
                JLatexMathPlugin.BuilderConfigure { builder ->
                    builder.blocksEnabled(true)
                    builder.blocksLegacy(false)
                    builder.inlinesEnabled(true)
                }
            ))
            .usePlugin(HtmlPlugin.create())
            .build()
    }

    AndroidView(
        modifier = Modifier.fillMaxWidth(),
        factory = { viewContext ->
            TextView(viewContext).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                )
                setTextColor(android.graphics.Color.rgb(240, 242, 232))
                setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 15f)
                setLineSpacing(0f, 1.08f)
                setPadding(0, 0, 0, 0)
                setBackgroundColor(android.graphics.Color.TRANSPARENT)
                movementMethod = LinkMovementMethod.getInstance()
            }
        },
        update = { textView -> markwon.setMarkdown(textView, MarkwonMathNormalizer.normalize(content)) }
    )
}

@Composable
private fun ChatScreen(
    messages: List<ChatMessage>, input: String, connected: Boolean, busy: Boolean, connectionMessage: String,
    activityLabel: String, activityLines: List<String>,
    onInput: (String) -> Unit, onSend: () -> Unit, onConnect: () -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        AppHeader("Chat", activityLabel = activityLabel)
        if (!connected) {
            Column(Modifier.padding(horizontal = 22.dp).fillMaxWidth().padding(bottom = 8.dp)) {
                Text("Not connected", color = Grey, fontSize = 13.sp)
                if (connectionMessage.isNotBlank()) {
                    Spacer(Modifier.height(5.dp))
                    Text(connectionMessage, color = if (connectionMessage.contains("not deployed", true) || connectionMessage.contains("not configured", true)) Grey else Red, fontSize = 13.sp, lineHeight = 18.sp)
                }
                Spacer(Modifier.height(8.dp))
                PrimaryButton(if (busy) "CONNECTING…" else "RETRY", onConnect, enabled = !busy)
            }
        }
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth().padding(horizontal = 22.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
            contentPadding = PaddingValues(top = 14.dp, bottom = 18.dp)
        ) {
            items(messages) { message ->
                val isUserMessage = message.role == "YOU"
                Column(
                    Modifier.fillMaxWidth().then(
                        if (isUserMessage) Modifier.background(Surface, RoundedCornerShape(3.dp))
                            .padding(horizontal = 14.dp, vertical = 12.dp)
                        else Modifier
                    )
                ) {
                    Text(
                        if (isUserMessage) "YOU" else message.role,
                        color = when (message.role) {
                            "SYSTEM" -> Red
                            "YOU" -> Grey
                            else -> Green
                        },
                        fontSize = 12.sp,
                        letterSpacing = 1.1.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = Mono
                    )
                    if (!isUserMessage && message.activityLines.isNotEmpty()) {
                        Spacer(Modifier.height(3.dp))
                        message.activityLines.forEach { line ->
                            Text(
                                line,
                                color = Grey,
                                fontSize = 10.sp,
                                lineHeight = 14.sp,
                                fontFamily = Mono
                            )
                        }
                    }
                    if (!isUserMessage && !message.modelLabel.isNullOrBlank()) {
                        Spacer(Modifier.height(3.dp))
                        Text(
                            message.modelLabel.orEmpty(),
                            color = Grey,
                            fontSize = 10.sp,
                            lineHeight = 14.sp,
                            fontFamily = Mono
                        )
                    }
                    Spacer(Modifier.height(7.dp))
                    MarkdownMessage(message.text)
                }
            }
            if (busy) item {
                Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text("OMNITRIX IS WORKING", color = Green, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                    Text(activityLabel, color = White, fontSize = 12.sp, lineHeight = 17.sp)
                    activityLines.takeLast(5).forEach { line ->
                        Text(line, color = Grey, fontSize = 11.sp, lineHeight = 15.sp)
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().background(Surface).imePadding().padding(10.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TerminalField(
                value = input, onValueChange = onInput, placeholder = "Message Omnitrix",
                modifier = Modifier.weight(1f), singleLine = false, enabled = connected && !busy
            )
            Button(
                onClick = onSend,
                enabled = connected && !busy && input.isNotBlank(),
                modifier = Modifier.height(52.dp),
                shape = RoundedCornerShape(2.dp),
                elevation = ButtonDefaults.buttonElevation(
                    defaultElevation = 0.dp,
                    pressedElevation = 0.dp,
                    focusedElevation = 0.dp,
                    hoveredElevation = 0.dp,
                    disabledElevation = 0.dp
                ),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Green,
                    contentColor = Black,
                    disabledContainerColor = SurfaceRaised,
                    disabledContentColor = Grey
                ),
                contentPadding = PaddingValues(horizontal = 14.dp)
            ) {
                Text(if (busy) "WAIT" else "SEND", color = if (busy) Grey else Black, fontFamily = Mono, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun RepoScreen(
    connected: Boolean,
    accountName: String,
    repositories: List<GitHubRepository>,
    selectedRepository: GitHubRepository?,
    folder: String,
    entries: List<RepoEntry>,
    selected: RepoEntry?,
    draft: String,
    original: String,
    busy: Boolean,
    message: String,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onOpen: (RepoEntry) -> Unit,
    onDraft: (String) -> Unit,
    onCommit: () -> Unit,
    onSignIn: () -> Unit,
    onSelectRepository: (GitHubRepository?) -> Unit,
    onNavigate: (String) -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        AppHeader(
            "Repository",
            if (selectedRepository == null) "Public repositories · @$accountName" else selectedRepository.fullName
        )
        when {
            selectedRepository == null -> {
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Repositories", color = White, fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    QuietButton("REFRESH", onRefresh)
                }
                if (message.isNotBlank()) {
                    Text(
                        message,
                        color = if (message.contains("fail", true) || message.contains("error", true)) Red else Grey,
                        fontSize = 13.sp,
                        lineHeight = 18.sp,
                        modifier = Modifier.padding(horizontal = 22.dp, vertical = 8.dp)
                    )
                }
                LazyColumn(
                    Modifier.fillMaxSize().padding(horizontal = 16.dp),
                    contentPadding = PaddingValues(bottom = 18.dp)
                ) {
                    if (busy) item { Text("Loading repositories…", color = Green, fontSize = 14.sp, modifier = Modifier.padding(12.dp)) }
                    items(repositories, key = { it.fullName }) { repository ->
                        Column(
                            Modifier.fillMaxWidth()
                                .clickable(enabled = !busy) { onSelectRepository(repository) }
                                .padding(horizontal = 8.dp, vertical = 13.dp),
                            verticalArrangement = Arrangement.spacedBy(3.dp)
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(repository.name, color = White, fontSize = 16.sp, lineHeight = 21.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                if (repository.isPrivate) Text("PRIVATE", color = Grey, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                            }
                            Text(repository.fullName, color = Green, fontSize = 12.sp, lineHeight = 17.sp)
                            if (repository.description.isNotBlank()) {
                                Text(repository.description, color = Grey, fontSize = 13.sp, lineHeight = 18.sp)
                            }
                            Box(Modifier.fillMaxWidth().padding(top = 8.dp).height(1.dp).background(SurfaceRaised))
                        }
                    }
                    if (repositories.isEmpty() && !busy && message.isBlank()) {
                        item { Text("No public repositories found.", color = Grey, fontSize = 14.sp, modifier = Modifier.padding(12.dp)) }
                    }
                }
            }
            selected != null -> {
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    QuietButton("BACK TO FOLDER", onBack)
                    Spacer(Modifier.weight(1f))
                    if (draft != original) Text("UNSAVED", color = Green, fontSize = 12.sp)
                }
                if (message.isNotBlank()) {
                    Text(message, color = if (message.contains("fail", true) || message.contains("error", true)) Red else Grey, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 5.dp))
                }
                TerminalField(
                    value = draft,
                    onValueChange = onDraft,
                    placeholder = "",
                    modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp).background(Surface, RoundedCornerShape(2.dp)),
                    singleLine = false,
                    enabled = !busy && connected && selectedRepository.fullName == REPOSITORY,
                    large = false
                )
                when {
                    selectedRepository.fullName != REPOSITORY -> {
                        Text(
                            "Read-only here. Direct commits are restricted to the Omnitrix repository.",
                            color = Grey, fontSize = 12.sp, lineHeight = 17.sp,
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)
                        )
                    }
                    connected -> {
                        PrimaryButton(
                            if (busy) "SAVING…" else "COMMIT TO MAIN",
                            onCommit,
                            enabled = !busy && draft != original,
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp)
                        )
                    }
                    else -> QuietButton("SIGN IN TO EDIT", onSignIn)
                }
            }
            else -> {
                Row(
                    Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 22.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "ALL REPOS",
                        color = Green,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.clickable { onSelectRepository(null) }.padding(vertical = 8.dp)
                    )
                    Text("  /  ", color = Grey, fontSize = 12.sp)
                    Text(
                        selectedRepository.name,
                        color = if (folder.isBlank()) White else Green,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.clickable { onNavigate("") }.padding(vertical = 8.dp)
                    )
                    var accumulated = ""
                    folder.split("/").filter { it.isNotBlank() }.forEach { segment ->
                        accumulated = if (accumulated.isBlank()) segment else accumulated + "/" + segment
                        Text("  /  ", color = Grey, fontSize = 12.sp)
                        val destination = accumulated
                        Text(
                            segment,
                            color = if (destination == folder) White else Green,
                            fontSize = 12.sp,
                            modifier = Modifier.clickable { onNavigate(destination) }.padding(vertical = 8.dp)
                        )
                    }
                }
                Row(
                    Modifier.fillMaxWidth().padding(start = 22.dp, end = 14.dp, top = 2.dp, bottom = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(if (busy) "Loading…" else if (folder.isBlank()) "Root folder" else "Folder contents", color = Grey, fontSize = 12.sp, modifier = Modifier.weight(1f))
                    if (folder.isNotBlank()) QuietButton("UP", onBack)
                    QuietButton("REFRESH", onRefresh)
                }
                if (message.isNotBlank()) {
                    Text(
                        message,
                        color = if (message.contains("fail", true) || message.contains("error", true)) Red else Grey,
                        fontSize = 13.sp,
                        lineHeight = 18.sp,
                        modifier = Modifier.padding(horizontal = 22.dp, vertical = 6.dp)
                    )
                }
                LazyColumn(
                    Modifier.fillMaxSize().padding(horizontal = 14.dp),
                    contentPadding = PaddingValues(bottom = 18.dp)
                ) {
                    items(entries, key = { it.path }) { entry ->
                        Column(
                            Modifier.fillMaxWidth()
                                .clickable(enabled = !busy) { onOpen(entry) }
                                .padding(horizontal = 8.dp, vertical = 13.dp)
                        ) {
                            Text(
                                entry.name + if (entry.type == "dir") "/" else "",
                                color = if (entry.type == "dir") Green else White,
                                fontSize = 15.sp,
                                lineHeight = 21.sp
                            )
                            Box(Modifier.fillMaxWidth().padding(top = 10.dp).height(1.dp).background(SurfaceRaised))
                        }
                    }
                    if (entries.isEmpty() && !busy && message.isBlank()) {
                        item { Text("No visible files in this folder.", color = Grey, fontSize = 13.sp, modifier = Modifier.padding(12.dp)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusScreen(
    runs: List<CiRun>, busy: Boolean, message: String,
    onRefresh: () -> Unit, onOpen: (String) -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        AppHeader("Runs")
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
        AppHeader("Account")
        Column(Modifier.padding(horizontal = 22.dp), verticalArrangement = Arrangement.spacedBy(15.dp)) {
            if (connected) {
                Text("@" + username, color = White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                QuietButton("SIGN OUT", onSignOut)
            } else if (device != null) {
                Text("AUTHORIZE THIS DEVICE", color = Green, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                Text(device.userCode, color = Green, fontSize = 34.sp, letterSpacing = 2.sp, fontWeight = FontWeight.Black, fontFamily = Pixel)
                Text("Enter this code on GitHub.", color = Grey, fontSize = 14.sp)
                PrimaryButton(if (busy) "WAITING FOR GITHUB…" else "OPEN GITHUB & CONTINUE", onAuthorize, enabled = !busy)
            } else {
                Text("GitHub Client ID", color = Grey, fontSize = 13.sp)
                TerminalField(clientId, onClientId, "Client ID", singleLine = true, capitalization = KeyboardCapitalization.None)
                QuietButton("GITHUB APP SETTINGS", onRegisterApp)
                PrimaryButton(if (busy) "PREPARING…" else "SIGN IN WITH GITHUB", onBeginSignIn, enabled = !busy && clientId.isNotBlank())
            }
            if (message.isNotBlank()) Text(message, color = Green, fontSize = 14.sp, lineHeight = 20.sp)
            if (error.isNotBlank()) Text(error, color = Red, fontSize = 14.sp, lineHeight = 20.sp)

            Spacer(Modifier.height(8.dp))
            Text("Chat backend", color = White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            Text(if (runtimeConnected) "Connected" else "Not connected", color = Grey, fontSize = 13.sp)
            QuietButton(if (showRuntimeSetup) "HIDE CHAT SETTINGS" else "CHAT SETTINGS", onToggleRuntime)
            if (showRuntimeSetup) {
                Text("Backend URL", color = Grey, fontSize = 13.sp)
                TerminalField(runtimeUrl, onRuntimeUrl, "HTTPS backend URL", singleLine = true, capitalization = KeyboardCapitalization.None, keyboardType = KeyboardType.Uri)
                Text("Access token", color = Grey, fontSize = 13.sp)
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
        modifier.fillMaxWidth().background(Surface, RoundedCornerShape(2.dp)).padding(horizontal = 14.dp, vertical = 13.dp),
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
        shape = RoundedCornerShape(2.dp),
        border = BorderStroke(1.dp, Green.copy(alpha = 0.72f)),
        colors = ButtonDefaults.buttonColors(
            containerColor = Black, contentColor = White,
            disabledContainerColor = SurfaceRaised, disabledContentColor = Grey
        ),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 15.dp)
    ) {
        Text(label, fontFamily = Pixel, fontSize = 14.sp, fontWeight = FontWeight.Bold, letterSpacing = .4.sp)
    }
}

@Composable
private fun QuietButton(label: String, onClick: () -> Unit) {
    Text(
        label, color = Green, fontSize = 13.sp, fontFamily = Pixel, fontWeight = FontWeight.Bold,
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
