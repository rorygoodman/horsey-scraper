package com.horsey.scraper

import com.google.gson.GsonBuilder
import java.io.File
import java.time.Instant

private const val OUTPUT_FILE = "betfair.json"

/**
 * Parses the regions CLI argument. First positional arg is a
 * comma-separated set of region IDs (case-insensitive, whitespace-tolerant).
 * If absent, defaults to `setOf("gb-ie")`.
 *
 * Region IDs come from [Regions.ALL]. Unknown IDs throw
 * `IllegalArgumentException` whose message lists the bad id(s) alongside
 * the valid set, so the caller can surface a clean error. An empty arg
 * (or one that parses to no ids) also throws.
 */
fun parseRegions(args: Array<String>): Set<String> {
    val raw = args.getOrNull(0) ?: return setOf("gb-ie")
    val ids = raw.split(",").map { it.trim().lowercase() }
        .filter { it.isNotEmpty() }
        .toSet()
    val known = Regions.ALL
    val unknown = ids - known
    require(unknown.isEmpty()) {
        "unknown region(s) ${unknown.joinToString(",")}; valid: ${known.sorted().joinToString(",")}"
    }
    require(ids.isNotEmpty()) {
        "regions must be non-empty; valid: ${known.sorted().joinToString(",")}"
    }
    return ids
}

/**
 * Entry point: one pass over today's racing in the chosen regions, fetched
 * from the Betfair Exchange REST API.
 *
 *   1. Parses regions from args[0] (default `gb-ie`).
 *   2. Loads credentials from `~/.horsey-scraper/credentials.json`.
 *   3. Logs in to identitysso.
 *   4. Fetches today's WIN markets and the explicit Top-N markets, then
 *      their prices in batches of ≤40 marketIds.
 *   5. Pivots into per-horse lay map and writes `data.json`.
 *
 * Output schema: see docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md
 * Migration:     see docs/superpowers/specs/2026-05-11-betfair-api-migration-design.md
 */
fun main(args: Array<String>) {
    val regions = try {
        parseRegions(args)
    } catch (e: IllegalArgumentException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(1)
    }

    val credentials = try {
        loadCredentials(defaultCredentialsPath())
    } catch (e: IllegalArgumentException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(2)
    }

    val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()

    println("Horsey Scraper — Betfair Exchange API — multi-market lay")
    println("regions=${regions.sorted().joinToString(",")}")
    println("=".repeat(80))

    val runStart = Instant.now()
    val client = BetfairClient(appKey = credentials.appKey)
    try {
        client.login(credentials.username, credentials.password)
    } catch (e: Exception) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(1)
    }

    println("\n[$runStart] Fetching today's race list…")
    val races = try {
        RaceListFetcher(client).fetch(regions)
    } catch (e: Exception) {
        System.err.println("Error fetching race list: ${e.message}")
        kotlin.system.exitProcess(1)
    }
    println("Found ${races.size} races today.")
    races.forEach { println("  ${it.offTime}  ${it.country}  ${it.venue}  (${it.raceId})") }

    val results: List<RaceOdds> = try {
        RaceOddsFetcher(client).fetch(races, regions)
    } catch (e: Exception) {
        System.err.println("Error fetching odds: ${e.message}")
        kotlin.system.exitProcess(1)
    }

    for (odds in results) {
        val markets = odds.marketScrapedAt.keys.joinToString(",") { it.name }
        println("  ${odds.offTime} ${odds.venue} (${odds.raceId}) → ${odds.runners.size} runners, markets=[$markets]")
    }
    val dropped = races.filter { r -> results.none { it.raceId == r.raceId } }
    for (r in dropped) {
        println("  ${r.offTime} ${r.venue} (${r.raceId}) DROPPED")
    }

    val output = ScrapeOutput(
        scrapedAt = runStart.toString(),
        raceCount = results.size,
        races = results
    )
    File(OUTPUT_FILE).writeText(gson.toJson(output))
    println("\nWrote $OUTPUT_FILE (${results.size} races)")
}
