package com.horsey.scraper

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.attribute.PosixFileAttributeView

data class Credentials(
    val username: String,
    val password: String,
    val appKey: String,
)

/**
 * Pure parser. Accepts a JSON object with string fields `username`,
 * `password`, `appKey`. Extra fields are ignored. Missing fields throw
 * `IllegalArgumentException` listing every offender in one message.
 */
fun parseCredentials(json: String): Credentials {
    val root: JsonObject = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        throw IllegalArgumentException("credentials JSON is not a valid object: ${e.message}")
    }
    val missing = mutableListOf<String>()
    fun stringOrMiss(key: String): String? {
        val el = root.get(key)
        if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isString) {
            missing += key; return null
        }
        return el.asString
    }
    val username = stringOrMiss("username")
    val password = stringOrMiss("password")
    val appKey   = stringOrMiss("appKey")
    require(missing.isEmpty()) {
        "credentials JSON missing or non-string fields: ${missing.joinToString(",")}"
    }
    return Credentials(username!!, password!!, appKey!!)
}

/** Default path: `~/.horsey-scraper/credentials.json`. */
fun defaultCredentialsPath(): Path =
    Paths.get(System.getProperty("user.home"), ".horsey-scraper", "credentials.json")

/**
 * Reads and parses the credentials file at [path]. Errors with the path
 * embedded for easy debugging. If the file mode is wider than `0600` on a
 * POSIX filesystem, prints a single warning to stderr and continues.
 */
fun loadCredentials(path: Path): Credentials {
    if (!Files.exists(path)) {
        throw IllegalArgumentException("credentials file not found: $path")
    }
    warnIfWorldReadable(path)
    val json = try {
        Files.readString(path)
    } catch (e: Exception) {
        throw IllegalArgumentException("failed to read $path: ${e.message}")
    }
    return parseCredentials(json)
}

private fun warnIfWorldReadable(path: Path) {
    val view = Files.getFileAttributeView(
        path, PosixFileAttributeView::class.java, LinkOption.NOFOLLOW_LINKS
    ) ?: return
    val perms = view.readAttributes().permissions()
    val tooOpen = perms.any { it.name.startsWith("GROUP_") || it.name.startsWith("OTHERS_") }
    if (tooOpen) {
        System.err.println("Warning: $path is readable by group/others; recommend `chmod 600`.")
    }
}
