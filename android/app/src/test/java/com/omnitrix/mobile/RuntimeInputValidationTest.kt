package com.omnitrix.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class RuntimeInputValidationTest {
    @Test
    fun acceptsAndNormalizesHttpsCodespaceUrl() {
        assertEquals(
            "https://example-8000.app.github.dev",
            RuntimeInputValidation.normalizeStudioUrl(" https://example-8000.app.github.dev/ ")
        )
    }

    @Test
    fun rejectsPlainHttpUrl() {
        assertThrows(IllegalArgumentException::class.java) {
            RuntimeInputValidation.normalizeStudioUrl("http://example-8000.app.github.dev")
        }
    }

    @Test
    fun rejectsUrlWithCredentialsOrQuery() {
        assertThrows(IllegalArgumentException::class.java) {
            RuntimeInputValidation.normalizeStudioUrl("https://user@example-8000.app.github.dev")
        }
        assertThrows(IllegalArgumentException::class.java) {
            RuntimeInputValidation.normalizeStudioUrl("https://example-8000.app.github.dev/?token=bad")
        }
    }

    @Test
    fun validatesTokenAndRemovesClipboardWhitespaceIncludingNewlines() {
        assertEquals(
            "long-token-value-1234567",
            RuntimeInputValidation.validateRuntimeToken("  long-token-\nvalue-1234567\n")
        )
        assertThrows(IllegalArgumentException::class.java) {
            RuntimeInputValidation.validateRuntimeToken("short")
        }
    }

    @Test
    fun rejectsCharactersOutsideUrlSafeTokenAlphabet() {
        assertThrows(IllegalArgumentException::class.java) {
            RuntimeInputValidation.validateRuntimeToken("long-token-value-1234567!")
        }
    }
    @Test
    fun validatesGithubClientIdWithoutAcceptingWhitespaceOrSymbols() {
        assertEquals("Iv1.abcd1234example", GitHubInputValidation.normalizeClientId(" Iv1.abcd1234example "))
        assertThrows(IllegalArgumentException::class.java) {
            GitHubInputValidation.normalizeClientId("not a client id")
        }
    }

    @Test
    fun repositoryPathAllowlistHidesInternalAndSensitivePaths() {
        assertEquals(true, GitHubInputValidation.isSafeRepoPath("android/app/src/MainActivity.kt"))
        assertEquals(true, GitHubInputValidation.isSafeRepoPath("README.md"))
        assertEquals(false, GitHubInputValidation.isSafeRepoPath(".github/workflows/ci.yml"))
        assertEquals(false, GitHubInputValidation.isSafeRepoPath("core/../README.md"))
        assertEquals(false, GitHubInputValidation.isSafeRepoPath("config/api_key.txt"))
        assertEquals(false, GitHubInputValidation.isSafeRepoPath("/README.md"))
    }

}
