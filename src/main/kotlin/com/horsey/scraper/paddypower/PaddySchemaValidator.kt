package com.horsey.scraper.paddypower

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

private val EW_PLACES_RANGE = 1..6

/**
 * Validates a `paddypower.json` payload string against the spec rules.
 * Returns an empty list if valid; otherwise a list of human-readable
 * error descriptions, one per violation.
 */
fun validatePaddyOutput(json: String): List<String> {
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
        if (!raceEl.isJsonObject) { errors += "$ctx: not an object"; return@forEachIndexed }
        val race = raceEl.asJsonObject

        requireString(race, "venue", errors)
        requireString(race, "country", errors)
        requireString(race, "offTime", errors) { v ->
            if (!isIsoOffsetDateTime(v)) errors += "$ctx.offTime not ISO-8601 with offset: '$v'"
        }
        requireString(race, "marketName", errors)
        requireString(race, "raceUrl", errors)
        requireString(race, "scrapedAt", errors) { v ->
            if (!isIsoUtc(v)) errors += "$ctx.scrapedAt not ISO-8601 UTC: '$v'"
        }

        val ewEl = race.get("eachWayTerms")
        if (ewEl != null && !ewEl.isJsonNull) {
            if (!ewEl.isJsonObject) {
                errors += "$ctx.eachWayTerms: not an object or null"
            } else {
                val ew = ewEl.asJsonObject
                val frac = ew.get("fraction")?.takeIf { it.isJsonPrimitive }?.asDouble
                if (frac == null || frac <= 0.0 || frac > 1.0) {
                    errors += "$ctx.eachWayTerms.fraction must be in (0,1], got $frac"
                }
                val places = ew.get("places")?.takeIf { it.isJsonPrimitive }?.asInt
                if (places == null || places !in EW_PLACES_RANGE) {
                    errors += "$ctx.eachWayTerms.places must be in $EW_PLACES_RANGE, got $places"
                }
            }
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
            val wp = r.get("winPrice")
            val raw = r.get("winPriceRaw")
            val wpNull = wp == null || wp.isJsonNull
            val rawNull = raw == null || raw.isJsonNull
            if (wpNull != rawNull) {
                errors += "$rctx: price parity violation — winPrice null=$wpNull, winPriceRaw null=$rawNull"
            }
            if (!wpNull && (!wp!!.isJsonPrimitive || !wp.asJsonPrimitive.isNumber)) {
                errors += "$rctx.winPrice: not a number"
            }
            if (!rawNull && (!raw!!.isJsonPrimitive || !raw.asJsonPrimitive.isString)) {
                errors += "$rctx.winPriceRaw: not a string"
            }
        }
    }
    return errors
}

private fun requireString(
    obj: JsonObject, key: String, errors: MutableList<String>,
    extra: (String) -> Unit = {},
): String? {
    val el = obj.get(key)
    if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isString) {
        errors += "$key: missing or not string"
        return null
    }
    val v = el.asString
    extra(v)
    return v
}

private fun requireInt(obj: JsonObject, key: String, errors: MutableList<String>): Int? {
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
