package com.omnitrix.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
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


    @Test
    fun detectsDirectVideoCreationPrompts() {
        assertTrue(VideoPromptIntent.isCreationPrompt(
            "Create a 12-second vertical science explainer video about induction stoves"
        ))
        assertTrue(VideoPromptIntent.isCreationPrompt(
            "Make a motion graphics animation about the life cycle of a star"
        ))
        assertTrue(VideoPromptIntent.isCreationPrompt(
            "Please generate a short video showing how magnetic induction works"
        ))
    }

    @Test
    fun doesNotRouteQuestionsOrOrdinaryChatToVideoStudio() {
        assertEquals(false, VideoPromptIntent.isCreationPrompt("Can you generate a motion graphics video?"))
        assertEquals(false, VideoPromptIntent.isCreationPrompt("How does an induction stove work?"))
        assertEquals(false, VideoPromptIntent.isCreationPrompt("Explain the process in a video"))
        assertEquals(false, VideoPromptIntent.isCreationPrompt(""))
    }

    @Test
    fun normalizesCommonLatexDelimitersForNativeRenderer() {
        val normalized = MarkwonMathNormalizer.normalize("Force: \\(F = ma\\)\n\\[E = mc^2\\]")
        assertTrue(normalized.contains("\$F = ma\$"))
        assertTrue(normalized.contains("\$\$\nE = mc^2\n\$\$"))
    }

    @Test
    fun doesNotNormalizeLatexInsideFencedOrInlineCode() {
        val original = "```latex\n\\(F = ma\\)\n```\n`\\[E = mc^2\\]`"
        assertEquals(original, MarkwonMathNormalizer.normalize(original))
    }

    @Test
    fun formatsAlertMarkersAsReadableBoldLabels() {
        val source = "> [!WARNING] Check the assumptions\n> More detail follows."
        val result = MarkwonMathNormalizer.normalize(source)
        assertTrue(result.contains("> **WARNING**  Check the assumptions"))
    }

}
