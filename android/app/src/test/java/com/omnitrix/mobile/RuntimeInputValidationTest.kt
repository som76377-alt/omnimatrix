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
    fun validatesTokenAndTrimsWhitespace() {
        assertEquals("long-token-value-1234567", RuntimeInputValidation.validateRuntimeToken(" long-token-value-1234567 "))
        assertThrows(IllegalArgumentException::class.java) {
            RuntimeInputValidation.validateRuntimeToken("short")
        }
    }
}
