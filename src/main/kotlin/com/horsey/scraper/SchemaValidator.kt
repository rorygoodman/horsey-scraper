package com.horsey.scraper

import com.google.gson.JsonElement
import com.google.gson.JsonParser
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

private val RACE_ID_REGEX = Regex("""^1\.\d+$""")
private val ALLOWED_COUNTRIES = setOf("GB", "IE", "US")
private val ALLOWED_MARKETS = setOf("WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5")

/**
 * Validates a `data.json` payload string against the spec rules.
 * Returns an empty list if the file is valid; otherwise a list of
 * human-readable error descriptions.
 *
 * Encodes the rules in the spec's "Edge-case rules" and "Acceptance" sections.
 */
fun validateScrapeOutput(json: String): List<String> {
    val errors = mutableListOf<String>()
    val root = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        return listOf("not valid JSON object: ${e.message}")
    }

    requireString(root, "scrapedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "top-level scrapedAt is not ISO-8601 UTC instant: '$v'"
    }
    val raceCount = requireInt(root, "raceCount", errors)
    val racesEl = root.get("races")
    if (racesEl == null || !racesEl.isJsonArray) {
        errors += "races: missing or not array"
        return errors
    }
    val races = racesEl.asJsonArray
    if (raceCount != null && raceCount != races.size()) {
        errors += "raceCount ($raceCount) != races.length (${races.size()})"
    }

    races.forEachIndexed { i, raceEl ->
        val ctx = "races[$i]"
        if (!raceEl.isJsonObject) {
            errors += "$ctx: not an object"
            return@forEachIndexed
        }
        val race = raceEl.asJsonObject

        requireString(race, "raceId", errors) { v ->
            if (!RACE_ID_REGEX.matches(v)) errors += "$ctx.raceId does not match ^1\\.\\d+$: '$v'"
        }
        requireString(race, "venue", errors)
        requireString(race, "country", errors) { v ->
            if (v !in ALLOWED_COUNTRIES) errors += "$ctx.country not in $ALLOWED_COUNTRIES: '$v'"
        }
        requireString(race, "offTime", errors) { v ->
            if (!isIsoOffsetDateTime(v)) errors += "$ctx.offTime not ISO-8601 with offset: '$v'"
        }
        requireString(race, "winMarketUrl", errors)
        requireString(race, "marketName", errors)

        val msaEl = race.get("marketScrapedAt")
        if (msaEl == null || !msaEl.isJsonObject) {
            errors += "$ctx.marketScrapedAt: missing or not object"
            return@forEachIndexed
        }
        val msa = msaEl.asJsonObject
        val msaKeys = msa.keySet()
        if (msaKeys.isEmpty()) errors += "$ctx.marketScrapedAt: empty (must contain at least WIN)"
        if ("WIN" !in msaKeys) errors += "$ctx.marketScrapedAt: missing required WIN key"
        for (key in msaKeys) {
            if (key !in ALLOWED_MARKETS) errors += "$ctx.marketScrapedAt: unknown market '$key'"
            val v = msa.get(key)?.asString ?: ""
            if (!isIsoUtc(v)) errors += "$ctx.marketScrapedAt.$key not ISO-8601 UTC: '$v'"
        }

        val runnersEl = race.get("runners")
        if (runnersEl == null || !runnersEl.isJsonArray) {
            errors += "$ctx.runners: missing or not array"
            return@forEachIndexed
        }
        runnersEl.asJsonArray.forEachIndexed { j, rEl ->
            val rctx = "$ctx.runners[$j]"
            if (!rEl.isJsonObject) { errors += "$rctx: not an object"; return@forEachIndexed }
            val r = rEl.asJsonObject
            requireString(r, "name", errors)
            val layEl = r.get("lay")
            if (layEl == null || !layEl.isJsonObject) {
                errors += "$rctx.lay: missing or not object"
                return@forEachIndexed
            }
            val layKeys = layEl.asJsonObject.keySet()
            if (layKeys != msaKeys) {
                errors += "$rctx.lay: key parity violation — has $layKeys, marketScrapedAt has $msaKeys"
            }
        }
    }
    return errors
}

private fun requireString(
    obj: com.google.gson.JsonObject,
    key: String,
    errors: MutableList<String>,
    extra: (String) -> Unit = {}
): String? {
    val el: JsonElement? = obj.get(key)
    if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isString) {
        errors += "$key: missing or not string"
        return null
    }
    val v = el.asString
    extra(v)
    return v
}

private fun requireInt(
    obj: com.google.gson.JsonObject,
    key: String,
    errors: MutableList<String>
): Int? {
    val el = obj.get(key)
    if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isNumber) {
        errors += "$key: missing or not number"
        return null
    }
    return el.asInt
}

private fun isIsoUtc(v: String): Boolean = try {
    java.time.Instant.parse(v); true
} catch (e: DateTimeParseException) { false }

private fun isIsoOffsetDateTime(v: String): Boolean = try {
    DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(v); true
} catch (e: DateTimeParseException) { false }
