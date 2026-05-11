package com.horsey.scraper

import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class CredentialsTest {
    @Test
    fun `parses happy path`() {
        val c = parseCredentials("""
            { "username": "alice", "password": "hunter2", "appKey": "key-123" }
        """.trimIndent())
        assertEquals(Credentials("alice", "hunter2", "key-123"), c)
    }

    @Test
    fun `ignores extra fields`() {
        val c = parseCredentials("""
            { "username": "a", "password": "b", "appKey": "k", "note": "ignore me" }
        """.trimIndent())
        assertEquals(Credentials("a", "b", "k"), c)
    }

    @Test
    fun `rejects missing username`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{ "password": "b", "appKey": "k" }""")
        }
        assertTrue("username" in (e.message ?: ""))
    }

    @Test
    fun `rejects missing password`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{ "username": "a", "appKey": "k" }""")
        }
        assertTrue("password" in (e.message ?: ""))
    }

    @Test
    fun `rejects missing appKey`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{ "username": "a", "password": "b" }""")
        }
        assertTrue("appKey" in (e.message ?: ""))
    }

    @Test
    fun `lists every missing field in one message`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{}""")
        }
        val m = e.message ?: ""
        assertTrue("username" in m && "password" in m && "appKey" in m,
            "message must list all missing fields: $m")
    }

    @Test
    fun `rejects malformed JSON`() {
        assertFailsWith<IllegalArgumentException> { parseCredentials("not json") }
    }

    @Test
    fun `loadCredentials reads file`() {
        val dir = Files.createTempDirectory("horsey-cred-test")
        val file = dir.resolve("credentials.json")
        Files.writeString(file, """{ "username": "a", "password": "b", "appKey": "k" }""")
        assertEquals(Credentials("a", "b", "k"), loadCredentials(file))
    }

    @Test
    fun `loadCredentials throws with path on missing file`() {
        val missing = Files.createTempDirectory("horsey-cred-test").resolve("nope.json")
        val e = assertFailsWith<IllegalArgumentException> { loadCredentials(missing) }
        assertTrue(missing.toString() in (e.message ?: ""),
            "message must name the missing file: ${e.message}")
    }

    @Test
    fun `loadCredentials warns on non-0600 mode but still loads`() {
        // POSIX only — skipped on Windows but our CI/dev is mac/linux.
        val dir = Files.createTempDirectory("horsey-cred-test")
        val file = dir.resolve("credentials.json")
        Files.writeString(file, """{ "username": "a", "password": "b", "appKey": "k" }""")
        Files.setPosixFilePermissions(file, PosixFilePermissions.fromString("rw-r--r--"))
        // Should not throw — warning is to stderr.
        val c = loadCredentials(file)
        assertEquals("a", c.username)
    }
}
