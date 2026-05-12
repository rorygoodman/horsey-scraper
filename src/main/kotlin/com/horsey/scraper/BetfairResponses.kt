package com.horsey.scraper

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val LONDON = ZoneId.of("Europe/London")

enum class MarketBookStatus { OPEN, OTHER }

data class MarketBookSnapshot(
    val status: MarketBookStatus,
    /** selectionId → best lay price; value is `null` when `availableToLay` is empty. */
    val layBySelectionId: Map<Long, Double?>,
)

/**
 * Parses the response body of `POST /api/login` and returns the ssoid token.
 * Throws `IllegalStateException` on any non-`SUCCESS` status or malformed
 * JSON. The error message includes the status string and, for the very
 * common `LOGIN_RESTRICTED` case, a hint about 2FA being incompatible with
 * interactive login.
 */
fun parseSsoid(json: String): String {
    val root: JsonObject = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        throw IllegalStateException("login response is not a valid JSON object: ${e.message}")
    }
    val statusEl = root.get("status")
    val status = if (statusEl != null && statusEl.isJsonPrimitive) statusEl.asString else "UNKNOWN"
    if (status != "SUCCESS") {
        val hint = if (status == "LOGIN_RESTRICTED")
            " — this likely means 2FA is enabled on the account. 2FA must be disabled for interactive login, or switch to cert-based login."
            else ""
        throw IllegalStateException("login failed with status=$status$hint")
    }
    val tokenEl = root.get("token")
    return if (tokenEl != null && tokenEl.isJsonPrimitive) tokenEl.asString
           else throw IllegalStateException("login response has SUCCESS status but no token")
}

/**
 * Builds a [Race] from a single `MarketCatalogue` JSON object. Returns null
 * if any required field is missing or unparseable.
 */
fun raceFromCatalogue(json: String): Race? {
    val root = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        return null
    }
    return raceFromCatalogue(root)
}

internal fun raceFromCatalogue(root: JsonObject): Race? {
    val marketId = root.get("marketId")?.asString ?: return null
    val startUtc = root.get("marketStartTime")?.asString ?: return null
    val event = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject ?: return null
    val venue = event.get("venue")?.asString ?: return null
    val country = event.get("countryCode")?.asString ?: return null

    val offTime = utcToLondon(startUtc) ?: return null
    return Race(
        raceId = marketId,
        venue = venue,
        country = country,
        offTime = offTime,
        winMarketUrl = "https://www.betfair.com/exchange/plus/horse-racing/market/$marketId",
    )
}

internal fun utcToLondon(isoUtc: String): String? = try {
    val parsed = OffsetDateTime.parse(isoUtc)
    parsed.atZoneSameInstant(LONDON).toOffsetDateTime()
        .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
} catch (e: Exception) {
    null
}

/**
 * Parses a single `MarketBook` JSON object into a [MarketBookSnapshot].
 * Status is `OPEN` only when the market is live; anything else
 * (`SUSPENDED`, `CLOSED`, unknown) collapses to `OTHER` and the caller
 * treats the market as a failed scrape.
 */
fun layPricesFromBook(json: String): MarketBookSnapshot {
    val root = JsonParser.parseString(json).asJsonObject
    return layPricesFromBook(root)
}

internal fun layPricesFromBook(root: JsonObject): MarketBookSnapshot {
    val status = if (root.get("status")?.asString == "OPEN") MarketBookStatus.OPEN
                 else MarketBookStatus.OTHER
    if (status != MarketBookStatus.OPEN) {
        return MarketBookSnapshot(status, emptyMap())
    }
    val runners = root.get("runners")?.asJsonArray ?: return MarketBookSnapshot(status, emptyMap())
    val out = linkedMapOf<Long, Double?>()
    for (rEl in runners) {
        if (!rEl.isJsonObject) continue
        val r = rEl.asJsonObject
        val sel = r.get("selectionId")?.asLong ?: continue
        val ex = r.get("ex")?.takeIf { it.isJsonObject }?.asJsonObject
        val lays = ex?.get("availableToLay")?.takeIf { it.isJsonArray }?.asJsonArray
        val firstPrice: Double? = lays?.firstOrNull { it.isJsonObject }
            ?.asJsonObject?.get("price")?.asDouble
        out[sel] = firstPrice
    }
    return MarketBookSnapshot(status, out)
}
