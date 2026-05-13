package com.horsey.scraper.paddypower

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val FRACTION_REGEX = Regex("""^(\d+)/(\d+)$""")
private val EVENS_FORMS = setOf("evens", "evs", "even")

/**
 * Converts a PaddyPower price string into decimal odds.
 *
 * Accepts simple integer fractions (`"5/2"` → `3.5`) and the "evens"
 * word forms (`"evens"`, `"EVS"`, `"Evens"` → `2.0`). Returns null for
 * `"SP"`, empty strings, whitespace-only, divide-by-zero, negatives,
 * non-integer fractions, or anything else that isn't a recognised
 * fractional odds string.
 *
 * Decimal odds = 1 + numerator/denominator.
 *
 * Kept as a utility for future bookmakers whose APIs only return
 * fractional strings. PaddyPower's `content-managed-page` endpoint
 * provides decimal odds directly, so this function is not used on the
 * PP scrape path; it's available for re-use.
 */
fun fractionalToDecimal(raw: String): Double? {
    val s = raw.trim()
    if (s.isEmpty()) return null
    if (s.lowercase() in EVENS_FORMS) return 2.0
    val m = FRACTION_REGEX.matchEntire(s) ?: return null
    val num = m.groupValues[1].toInt()
    val den = m.groupValues[2].toInt()
    if (den == 0) return null
    return 1.0 + num.toDouble() / den.toDouble()
}

private val LONDON = ZoneId.of("Europe/London")
private val HHMM = DateTimeFormatter.ofPattern("HH:mm")

// PaddyPower's synthetic placeholders that appear in every market and are
// not actual horses. Filter by name (selection ids 10518227, 10518230,
// 327679 would work too; name-based is more portable across endpoints).
private val SYNTHETIC_RUNNER_NAMES =
    setOf("Unnamed Favourite", "Unnamed 2nd Favourite", "The Field")

/**
 * Shreds a PaddyPower next-races JSON response into [PaddyRace] objects.
 *
 * Expected shape (see test class KDoc for full details):
 *   `attachments.races[id]`   → race metadata, joins to `markets[winMarketId]`
 *   `attachments.markets[id]` → runners, EW terms, exchangeMarketId
 *
 * Drops races that:
 *   - have no country code (region filter would be unsafe)
 *   - have no joined WIN market
 *   - have zero non-synthetic, non-empty runners after filtering
 *
 * Non-runners (`runnerStatus = "REMOVED"`) are preserved in the runner list
 * with both price fields null. Each race carries the [nowProvider]'s
 * timestamp as `scrapedAt`.
 */
fun parsePaddyNextRaces(
    json: String,
    nowProvider: () -> Instant = { Instant.now() },
): List<PaddyRace> {
    val root = JsonParser.parseString(json).asJsonObject
    val attachments = root.get("attachments")?.takeIf { it.isJsonObject }?.asJsonObject
        ?: return emptyList()
    val racesObj = attachments.get("races")?.takeIf { it.isJsonObject }?.asJsonObject
        ?: return emptyList()
    val marketsObj = attachments.get("markets")?.takeIf { it.isJsonObject }?.asJsonObject
        ?: return emptyList()

    val scrapedAt = nowProvider().toString()
    val out = mutableListOf<PaddyRace>()
    for ((_, raceEl) in racesObj.entrySet()) {
        if (!raceEl.isJsonObject) continue
        val race = paddyRaceFromJson(raceEl.asJsonObject, marketsObj, scrapedAt) ?: continue
        out += race
    }
    return out
}

private fun paddyRaceFromJson(
    raceJson: JsonObject,
    marketsObj: JsonObject,
    scrapedAt: String,
): PaddyRace? {
    val venue = raceJson.string("venue") ?: return null
    val country = raceJson.string("countryCode")?.takeIf { it.isNotBlank() } ?: run {
        System.err.println("paddy: dropping race with no country at venue=$venue")
        return null
    }
    val startTimeUtc = raceJson.string("startTime") ?: return null
    val offTime = utcToLondon(startTimeUtc) ?: return null
    val winMarketId = raceJson.string("winMarketId") ?: return null
    val raceType = raceJson.string("winMarketName") ?: ""

    val marketJson = marketsObj.get(winMarketId)?.takeIf { it.isJsonObject }?.asJsonObject
        ?: run {
            System.err.println("paddy: dropping race with no market for winMarketId=$winMarketId at venue=$venue")
            return null
        }

    val runners = parsePaddyRunners(marketJson)
    if (runners.isEmpty()) {
        System.err.println("paddy: dropping race with zero runners: $venue $startTimeUtc")
        return null
    }

    val ew = parseStructuredEachWay(marketJson)
    val betfairId = marketJson.string("exchangeMarketId")

    val time = OffsetDateTime.parse(offTime).format(HHMM)
    val marketName = if (raceType.isBlank()) "$time $venue" else "$time $venue - $raceType"

    return PaddyRace(
        venue = venue,
        country = country,
        offTime = offTime,
        marketName = marketName,
        raceUrl = "",  // PaddyPower doesn't expose a per-race deep link in this endpoint
        scrapedAt = scrapedAt,
        betfairWinMarketId = betfairId,
        eachWayTerms = ew,
        runners = runners,
    )
}

private fun parsePaddyRunners(marketJson: JsonObject): List<PaddyRunner> {
    val runners = marketJson.get("runners")?.takeIf { it.isJsonArray }?.asJsonArray
        ?: return emptyList()
    val out = mutableListOf<PaddyRunner>()
    for (rEl in runners) {
        if (!rEl.isJsonObject) continue
        val r = rEl.asJsonObject
        val name = r.string("runnerName") ?: continue
        if (name in SYNTHETIC_RUNNER_NAMES) continue
        val selectionId = r.long("selectionId")
        val status = r.string("runnerStatus") ?: "ACTIVE"
        val odds = r.get("winRunnerOdds")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.get("trueOdds")?.takeIf { it.isJsonObject }?.asJsonObject
        val isActiveWithOdds = status == "ACTIVE" && odds != null
        val decimalVal: Double? = odds
            ?.get("decimalOdds")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.double("decimalOdds")
            ?.takeIf { isActiveWithOdds }
        val fractionalVal: String? = odds
            ?.get("fractionalOdds")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.let { fOdds ->
                val n = fOdds.int("numerator") ?: return@let null
                val d = fOdds.int("denominator") ?: return@let null
                "$n/$d"
            }
            ?.takeIf { isActiveWithOdds }
        // Parity invariant (see PaddyRunner KDoc): both populated or both null.
        // If either side is missing (e.g. malformed fractionalOdds), null both.
        val bothPresent = decimalVal != null && fractionalVal != null
        val winPrice = if (bothPresent) decimalVal else null
        val winPriceRaw = if (bothPresent) fractionalVal else null
        out += PaddyRunner(
            name = name,
            selectionId = selectionId,
            winPrice = winPrice,
            winPriceRaw = winPriceRaw,
        )
    }
    return out
}

private fun parseStructuredEachWay(marketJson: JsonObject): EachWayTerms? {
    val available = marketJson.get("eachwayAvailable")?.takeIf { it.isJsonPrimitive }
        ?.asJsonPrimitive?.takeIf { it.isBoolean }?.asBoolean ?: true
    if (!available) return null
    val places = marketJson.int("numberOfPlaces") ?: return null
    if (places <= 0) return null
    val frac = marketJson.get("placeFraction")?.takeIf { it.isJsonObject }?.asJsonObject ?: return null
    val num = frac.int("numerator") ?: return null
    val den = frac.int("denominator") ?: return null
    if (den == 0) return null
    val fraction = num.toDouble() / den.toDouble()
    if (fraction <= 0.0 || fraction > 1.0) return null
    return EachWayTerms(fraction, places)
}

/**
 * Converts a UTC ISO-8601 instant (e.g. `"2026-05-14T16:40:00.000Z"`) to a
 * Europe/London ISO-8601 string with offset (`"2026-05-14T17:40:00+01:00"`
 * in BST or `"…Z"` in GMT). Returns null on parse failure.
 */
internal fun utcToLondon(isoUtc: String): String? = try {
    OffsetDateTime.parse(isoUtc)
        .atZoneSameInstant(LONDON).toOffsetDateTime()
        .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
} catch (e: Exception) {
    null
}

// Tiny JSON helpers — keep guards uniform across this file.
private fun JsonObject.string(key: String): String? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
private fun JsonObject.int(key: String): Int? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asInt
private fun JsonObject.long(key: String): Long? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asLong
private fun JsonObject.double(key: String): Double? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asDouble
