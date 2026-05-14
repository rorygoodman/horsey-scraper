package com.horsey.scraper.arb

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

private val EW_PLACES_RANGE = 2..5
private val ALLOWED_TOP_N = setOf("TOP_2", "TOP_3", "TOP_4", "TOP_5")

/**
 * Validates an `arbs.json` payload string against the spec rules.
 * Returns an empty list if valid; otherwise a list of human-readable
 * error descriptions, one per violation.
 */
fun validateArbsOutput(json: String): List<String> {
    val errors = mutableListOf<String>()
    val root = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        return listOf("not valid JSON object: ${e.message}")
    }

    requireString(root, "computedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "computedAt is not ISO-8601 UTC instant: '$v'"
    }
    requireString(root, "betfairScrapedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "betfairScrapedAt is not ISO-8601 UTC instant: '$v'"
    }
    requireString(root, "paddypowerScrapedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "paddypowerScrapedAt is not ISO-8601 UTC instant: '$v'"
    }
    val arbCount = requireInt(root, "arbCount", errors)
    val arbsEl = root.get("arbs")
    if (arbsEl == null || !arbsEl.isJsonArray) {
        errors += "arbs: missing or not array"
        return errors
    }
    val arbs = arbsEl.asJsonArray
    if (arbCount != null && arbCount != arbs.size()) {
        errors += "arbCount ($arbCount) != arbs.length (${arbs.size()})"
    }

    arbs.forEachIndexed { i, arbEl ->
        val ctx = "arbs[$i]"
        if (!arbEl.isJsonObject) { errors += "$ctx: not an object"; return@forEachIndexed }
        val arb = arbEl.asJsonObject

        requireString(arb, "venue", errors)
        requireString(arb, "country", errors)
        requireString(arb, "offTime", errors) { v ->
            if (!isIsoOffsetDateTime(v)) errors += "$ctx.offTime not ISO-8601 with offset: '$v'"
        }
        requireString(arb, "marketName", errors)
        requireString(arb, "betfairWinMarketId", errors)

        val marginEl = arb.get("margin")
        if (marginEl == null || !marginEl.isJsonPrimitive || !marginEl.asJsonPrimitive.isNumber) {
            errors += "$ctx.margin: missing or not a number"
        } else if (marginEl.asDouble <= 0.0) {
            errors += "$ctx.margin must be > 0, got ${marginEl.asDouble}"
        }

        val runnerEl = arb.get("runner")
        if (runnerEl == null || !runnerEl.isJsonObject) {
            errors += "$ctx.runner: missing or not an object"
        } else {
            val runner = runnerEl.asJsonObject
            requireString(runner, "name", errors)
            val selEl = runner.get("selectionId")
            if (selEl == null || !selEl.isJsonPrimitive || !selEl.asJsonPrimitive.isNumber) {
                errors += "$ctx.runner.selectionId: missing or not a number"
            }
        }

        validatePaddyLeg(arb.get("paddypower"), "$ctx.paddypower", errors)
        validateBetfairLeg(arb.get("betfair"), "$ctx.betfair", errors)
    }
    return errors
}

private fun validatePaddyLeg(el: com.google.gson.JsonElement?, ctx: String, errors: MutableList<String>) {
    if (el == null || !el.isJsonObject) {
        errors += "$ctx: missing or not an object"; return
    }
    val pp = el.asJsonObject
    val winPrice = pp.get("winPrice")
    if (winPrice == null || !winPrice.isJsonPrimitive || !winPrice.asJsonPrimitive.isNumber) {
        errors += "$ctx.winPrice: missing or not a number"
    }
    requireString(pp, "winPriceRaw", errors)

    val ewEl = pp.get("eachWayTerms")
    if (ewEl == null || !ewEl.isJsonObject) {
        errors += "$ctx.eachWayTerms: missing or not an object"; return
    }
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

private fun validateBetfairLeg(el: com.google.gson.JsonElement?, ctx: String, errors: MutableList<String>) {
    if (el == null || !el.isJsonObject) {
        errors += "$ctx: missing or not an object"; return
    }
    val bf = el.asJsonObject
    for (key in listOf("winLay", "topNLay")) {
        val v = bf.get(key)
        if (v == null || !v.isJsonPrimitive || !v.asJsonPrimitive.isNumber) {
            errors += "$ctx.$key: missing or not a number"
        }
    }
    val topNType = bf.get("topNType")?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
    if (topNType == null) {
        errors += "$ctx.topNType: missing or not a string"
    } else if (topNType !in ALLOWED_TOP_N) {
        errors += "$ctx.topNType: '$topNType' not in $ALLOWED_TOP_N"
    }
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
