package com.horsey.scraper

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.Instant

data class PlaceMarketEntry(
    val marketId: String,
    val type: MarketType,
    /** selectionId → runnerName, as published by the catalogue for this market. */
    val runners: Map<Long, String>,
)

/** Splits a list into chunks of at most 40 elements (Betfair's `listMarketBook` cap). */
fun <T> chunkOf40(items: List<T>): List<List<T>> =
    if (items.isEmpty()) emptyList() else items.chunked(40)

/**
 * Parses a PLACE `listMarketCatalogue` response: classifies each market via
 * [classifyTopN] and groups the survivors by `event.id`. Anything that
 * doesn't classify (To Be Placed, mismatched winners, etc.) is dropped.
 */
fun parseCataloguePlaceMarkets(json: String): Map<String, List<PlaceMarketEntry>> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, MutableList<PlaceMarketEntry>>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val name = root.get("marketName")?.asString ?: continue
        val desc = root.get("description")?.takeIf { it.isJsonObject }?.asJsonObject ?: continue
        val numberOfWinners = desc.get("numberOfWinners")?.asInt ?: continue
        val type = classifyTopN(name, numberOfWinners) ?: continue
        val marketId = root.get("marketId")?.asString ?: continue
        val eventId = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.get("id")?.asString ?: continue
        out.getOrPut(eventId) { mutableListOf() }.add(
            PlaceMarketEntry(marketId, type, runnerMap(root))
        )
    }
    return out
}

/**
 * Parses a WIN `listMarketCatalogue` response into a marketId → ordered list
 * of `(selectionId, runnerName)` pairs. Order is the catalogue order, which
 * matches the WIN page display order on the Betfair Exchange.
 */
fun parseWinCatalogueRunners(json: String): Map<String, List<Pair<Long, String>>> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, List<Pair<Long, String>>>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val marketId = root.get("marketId")?.asString ?: continue
        val runners = root.get("runners")?.takeIf { it.isJsonArray }?.asJsonArray ?: continue
        val pairs = mutableListOf<Pair<Long, String>>()
        for (rEl in runners) {
            if (!rEl.isJsonObject) continue
            val r = rEl.asJsonObject
            val sel = r.get("selectionId")?.asLong ?: continue
            val name = r.get("runnerName")?.asString ?: continue
            pairs += sel to name
        }
        out[marketId] = pairs
    }
    return out
}

/** Parses a `listMarketBook` array response into marketId → snapshot. */
fun parseBookSnapshots(json: String): Map<String, MarketBookSnapshot> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, MarketBookSnapshot>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val marketId = root.get("marketId")?.asString ?: continue
        out[marketId] = layPricesFromBook(root)
    }
    return out
}

private fun runnerMap(catalogue: JsonObject): Map<Long, String> {
    val runners = catalogue.get("runners")?.takeIf { it.isJsonArray }?.asJsonArray ?: return emptyMap()
    val out = linkedMapOf<Long, String>()
    for (rEl in runners) {
        if (!rEl.isJsonObject) continue
        val r = rEl.asJsonObject
        val sel = r.get("selectionId")?.asLong ?: continue
        val name = r.get("runnerName")?.asString ?: continue
        out[sel] = name
    }
    return out
}

/**
 * Joins race metadata, catalogue runners, PLACE classifications, and price
 * snapshots into the final `List<RaceOdds>`. Rules mirror the Selenium
 * pipeline: WIN failure (`status != OPEN`) drops the race; any TOP_N with
 * `status != OPEN` is treated as a failed scrape (key omitted everywhere).
 *
 * Pure function: caller provides the single `scrapedAt` timestamp (captured
 * after all `listMarketBook` calls have returned) and the formatted
 * `winMarketName`.
 */
fun joinScrapes(
    races: List<Race>,
    placeMarketsByRaceId: Map<String, List<PlaceMarketEntry>>,
    snapshots: Map<String, MarketBookSnapshot>,
    winRunners: Map<String, List<Pair<Long, String>>>,
    winMarketName: String,
    scrapedAt: String,
): List<RaceOdds> {
    val out = mutableListOf<RaceOdds>()
    for (race in races) {
        val winSnap = snapshots[race.raceId] ?: continue
        if (winSnap.status != MarketBookStatus.OPEN) continue

        val nameOrder = winRunners[race.raceId] ?: continue
        val scrapes = linkedMapOf<MarketType, MarketScrape>(
            MarketType.WIN to MarketScrape(
                type = MarketType.WIN,
                scrapedAt = scrapedAt,
                runners = nameOrder.map { (sel, name) -> name to winSnap.layBySelectionId[sel] },
            )
        )

        val placeMarkets = placeMarketsByRaceId[race.raceId].orEmpty()
        for (place in placeMarkets) {
            val snap = snapshots[place.marketId] ?: continue
            if (snap.status != MarketBookStatus.OPEN) continue
            val rows = place.runners.entries.map { (sel, name) ->
                name to snap.layBySelectionId[sel]
            }
            scrapes[place.type] = MarketScrape(
                type = place.type,
                scrapedAt = scrapedAt,
                runners = rows,
            )
        }

        val odds = assembleRaceOdds(race, winMarketName, scrapes) ?: continue
        out += odds
    }
    return out
}

/**
 * Fetches WIN + classified Top-N markets for the supplied races. Performs:
 *
 *  1. One catalogue call for PLACE markets in the same time window and
 *     country set as the races.
 *  2. One catalogue call for WIN markets (sources runner names, race-type
 *     snippet, and the marketId → eventId map used to join the PLACE
 *     results back to races).
 *  3. Batched `listMarketBook` calls (≤40 marketIds per chunk) covering the
 *     WIN + classified PLACE markets.
 *  4. One call to [joinScrapes] per race with a single shared `scrapedAt`
 *     timestamp captured immediately after the last book response.
 *
 * Per-race `marketName` is formatted with [formatMarketName]; the race-type
 * snippet comes from the WIN catalogue's `marketName` field.
 */
class RaceOddsFetcher(
    private val client: BetfairClient,
    private val nowProvider: () -> Instant = { Instant.now() },
) {
    fun fetch(races: List<Race>, regions: Set<String>): List<RaceOdds> {
        if (races.isEmpty()) return emptyList()
        val countries = Regions.countriesForAll(regions).sorted()
        val (from, to) = londonDayWindowUtc(java.time.LocalDate.now(java.time.ZoneId.of("Europe/London")))

        // PLACE catalogue.
        val placeBody = buildCatalogueBody(
            marketTypeCodes = listOf("PLACE"),
            countries = countries,
            from = from, to = to,
            projection = listOf("EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val placeJson = client.listMarketCatalogue(placeBody)
        val placeByEvent = parseCataloguePlaceMarkets(placeJson)

        // WIN catalogue (re-fetched to grab runner names + raceType + eventIds).
        val winBody = buildCatalogueBody(
            marketTypeCodes = listOf("WIN"),
            countries = countries,
            from = from, to = to,
            projection = listOf("EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val winJson = client.listMarketCatalogue(winBody)
        val winRunners = parseWinCatalogueRunners(winJson)
        val winRaceTypeByRaceId = parseWinRaceTypes(winJson)
        val eventIdByRaceId = parseWinEventIds(winJson)

        // Rekey placeByEvent from eventId → raceId using the WIN catalogue's
        // marketId↔eventId map (built once, used many).
        val raceIdByEventId = eventIdByRaceId.entries.associate { (rid, eid) -> eid to rid }
        val placeByRaceId = mutableMapOf<String, List<PlaceMarketEntry>>()
        for ((eventId, list) in placeByEvent) {
            val raceId = raceIdByEventId[eventId] ?: continue
            placeByRaceId[raceId] = list
        }

        // Gather marketIds and fetch prices in batches.
        val allMarketIds = (races.map { it.raceId } +
            placeByRaceId.values.flatten().map { it.marketId }).distinct()
        val snapshots = linkedMapOf<String, MarketBookSnapshot>()
        for (chunk in chunkOf40(allMarketIds)) {
            val resp = client.listMarketBook(buildBookBody(chunk))
            snapshots.putAll(parseBookSnapshots(resp))
        }

        // Single timestamp captured after all book responses are in. The
        // resolution is coarser than per-batch, but matches the schema's
        // "scrapedAt = when we observed this market" semantics within the
        // few-hundred-ms it takes the book calls to complete.
        val scrapedAt = nowProvider().toString()

        val out = mutableListOf<RaceOdds>()
        for (race in races) {
            val raceType = winRaceTypeByRaceId[race.raceId] ?: ""
            val marketName = formatMarketName(race, raceType)
            out += joinScrapes(
                races = listOf(race),
                placeMarketsByRaceId = mapOf(race.raceId to (placeByRaceId[race.raceId] ?: emptyList())),
                snapshots = snapshots,
                winRunners = winRunners,
                winMarketName = marketName,
                scrapedAt = scrapedAt,
            )
        }
        return out
    }
}

/**
 * Returns marketId → its WIN catalogue `marketName` (used as the race-type
 * snippet for the spec's `"<HH:mm> <venue> - <race type>"` format).
 */
fun parseWinRaceTypes(json: String): Map<String, String> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, String>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val mid = root.get("marketId")?.asString ?: continue
        val name = root.get("marketName")?.asString ?: ""
        out[mid] = name
    }
    return out
}

/** Returns marketId → eventId from a WIN `listMarketCatalogue` response. */
fun parseWinEventIds(json: String): Map<String, String> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, String>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val mid = root.get("marketId")?.asString ?: continue
        val event = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject ?: continue
        val eid = event.get("id")?.asString ?: continue
        out[mid] = eid
    }
    return out
}
