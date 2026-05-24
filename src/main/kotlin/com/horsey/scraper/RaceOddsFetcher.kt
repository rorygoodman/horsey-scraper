package com.horsey.scraper

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.Instant

data class PlaceMarketEntry(
    val marketId: String,
    val type: MarketType,
    /** Betfair event id this market belongs to. Multiple races at one venue share one event. */
    val eventId: String,
    /** The market's start time (ISO-8601 UTC). Equals the race's WIN `marketStartTime`. */
    val marketTime: String,
    /** selectionId → runnerName, as published by the catalogue for this market. */
    val runners: Map<Long, String>,
)

/** Splits a list into chunks of at most 40 elements (Betfair's `listMarketBook` cap). */
fun <T> chunkOf40(items: List<T>): List<List<T>> =
    if (items.isEmpty()) emptyList() else items.chunked(40)

/**
 * Parses a PLACE `listMarketCatalogue` response: classifies each market via
 * [classifyTopN] and returns one [PlaceMarketEntry] per surviving market.
 * Anything that doesn't classify (To Be Placed, mismatched winners, etc.)
 * is dropped. Markets without `description.marketTime` are also dropped —
 * we need the marketTime to bind each PLACE market to its specific race
 * (the Betfair event id alone is ambiguous across a multi-race meeting).
 */
fun parseCataloguePlaceMarkets(json: String): List<PlaceMarketEntry> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = mutableListOf<PlaceMarketEntry>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val name = root.get("marketName")?.asString ?: continue
        val desc = root.get("description")?.takeIf { it.isJsonObject }?.asJsonObject ?: continue
        // numberOfWinners is null in practice on the API's catalogue projection.
        // Classifier accepts null and falls back to the name pattern.
        val numberOfWinners = desc.get("numberOfWinners")?.takeIf { it.isJsonPrimitive }?.asInt
        val type = classifyTopN(name, numberOfWinners) ?: continue
        val marketTime = desc.get("marketTime")?.takeIf { it.isJsonPrimitive }?.asString ?: continue
        val marketId = root.get("marketId")?.asString ?: continue
        val eventId = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.get("id")?.asString ?: continue
        out += PlaceMarketEntry(marketId, type, eventId, marketTime, runnerMap(root))
    }
    return out
}

/**
 * Groups [entries] by `(eventId, marketTime)` and rekeys them to raceId
 * using [raceKeyByRaceId] (a `raceId → (eventId, marketTime)` map built
 * from the WIN catalogue). Entries whose key doesn't appear in
 * [raceKeyByRaceId] are dropped. Within a multi-race Betfair event this
 * is what ensures each race only sees its own Top-N markets.
 */
fun placeMarketsByRaceId(
    entries: List<PlaceMarketEntry>,
    raceKeyByRaceId: Map<String, Pair<String, String>>,
): Map<String, List<PlaceMarketEntry>> {
    val raceIdByKey = raceKeyByRaceId.entries.associate { (rid, key) -> key to rid }
    val out = linkedMapOf<String, MutableList<PlaceMarketEntry>>()
    for (entry in entries) {
        val raceId = raceIdByKey[entry.eventId to entry.marketTime] ?: continue
        out.getOrPut(raceId) { mutableListOf() }.add(entry)
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
                runners = nameOrder.map { (sel, name) ->
                    RunnerEntry(selectionId = sel, name = name, lay = winSnap.layBySelectionId[sel])
                },
            )
        )

        val placeMarkets = placeMarketsByRaceId[race.raceId].orEmpty()
        for (place in placeMarkets) {
            val snap = snapshots[place.marketId] ?: continue
            if (snap.status != MarketBookStatus.OPEN) continue
            val rows = place.runners.entries.map { (sel, name) ->
                RunnerEntry(selectionId = sel, name = name, lay = snap.layBySelectionId[sel])
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
        // PLACE = standard "To Be Placed" (rejected by the classifier).
        // OTHER_PLACE = the explicit "N TBP" / "Top N Finish" markets.
        // We fetch both and let `parseCataloguePlaceMarkets` filter by name.
        val placeBody = buildCatalogueBody(
            marketTypeCodes = listOf("PLACE", "OTHER_PLACE"),
            countries = countries,
            from = from, to = to,
            projection = listOf("EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val placeJson = client.listMarketCatalogue(placeBody)
        val placeEntries = parseCataloguePlaceMarkets(placeJson)

        // WIN catalogue (re-fetched to grab runner names + raceType + race keys).
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
        val raceKeyByRaceId = parseWinRaceKeys(winJson)

        // Bind each PLACE market to its specific race via (eventId, marketTime).
        // The Betfair event id alone collides across the day's races at one venue.
        val placeByRaceId = placeMarketsByRaceId(placeEntries, raceKeyByRaceId)

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

/**
 * Returns raceId (WIN marketId) → `(eventId, marketStartTime)` from a WIN
 * `listMarketCatalogue` response. The pair uniquely identifies a race
 * within a multi-race Betfair event and is the key used to bind PLACE
 * markets back to the right race.
 */
fun parseWinRaceKeys(json: String): Map<String, Pair<String, String>> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, Pair<String, String>>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val mid = root.get("marketId")?.asString ?: continue
        val event = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject ?: continue
        val eid = event.get("id")?.asString ?: continue
        val mst = root.get("marketStartTime")?.takeIf { it.isJsonPrimitive }?.asString ?: continue
        out[mid] = eid to mst
    }
    return out
}
