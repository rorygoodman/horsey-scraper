package com.horsey.scraper.arb

import com.google.gson.GsonBuilder
import com.horsey.scraper.ScrapeOutput
import com.horsey.scraper.paddypower.PaddyOutput
import com.horsey.scraper.paddypower.validatePaddyOutput
import com.horsey.scraper.validateScrapeOutput
import java.io.File
import java.time.Instant

data class ArbCliPaths(
    val betfairInput: String,
    val paddypowerInput: String,
    val output: String,
)

/**
 * Two CLI modes only:
 *   - 0 args: defaults (betfair.json, paddypower.json, arbs.json in cwd).
 *   - 3 args: explicit paths in the order betfair-in, paddy-in, output.
 * Anything else throws `IllegalArgumentException` so the caller can
 * surface a clean usage message and exit non-zero.
 */
fun parseArbCliArgs(args: Array<String>): ArbCliPaths = when (args.size) {
    0 -> ArbCliPaths("betfair.json", "paddypower.json", "arbs.json")
    3 -> ArbCliPaths(args[0], args[1], args[2])
    else -> throw IllegalArgumentException(
        "usage: ArbMain                                          # all defaults\n" +
        "       ArbMain <betfair-in> <paddypower-in> <arbs-out>  # all explicit"
    )
}

/**
 * Entry point. Reads the two snapshot files, validates each against
 * its own schema, computes arbs, writes `arbs.json`.
 *
 * Exit codes:
 *   - 0: ran cleanly (even if zero arbs).
 *   - 1: bad CLI usage.
 *   - 2: input file missing, unparseable, or fails its schema validator.
 */
fun main(args: Array<String>) {
    val paths = try {
        parseArbCliArgs(args)
    } catch (e: IllegalArgumentException) {
        System.err.println(e.message)
        kotlin.system.exitProcess(1)
    }

    val betfairText = readOrExit(paths.betfairInput)
    val paddyText = readOrExit(paths.paddypowerInput)

    val betfairErrors = validateScrapeOutput(betfairText)
    if (betfairErrors.isNotEmpty()) {
        System.err.println("Error: ${paths.betfairInput} fails Betfair schema:")
        betfairErrors.forEach { System.err.println("  - $it") }
        kotlin.system.exitProcess(2)
    }
    val paddyErrors = validatePaddyOutput(paddyText)
    if (paddyErrors.isNotEmpty()) {
        System.err.println("Error: ${paths.paddypowerInput} fails PaddyPower schema:")
        paddyErrors.forEach { System.err.println("  - $it") }
        kotlin.system.exitProcess(2)
    }

    val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()
    val betfair = try {
        gson.fromJson(betfairText, ScrapeOutput::class.java)
    } catch (e: Exception) {
        System.err.println("Error: ${paths.betfairInput} could not be deserialised: ${e.message}")
        kotlin.system.exitProcess(2)
    }
    val paddy = try {
        gson.fromJson(paddyText, PaddyOutput::class.java)
    } catch (e: Exception) {
        System.err.println("Error: ${paths.paddypowerInput} could not be deserialised: ${e.message}")
        kotlin.system.exitProcess(2)
    }

    val computedAt = Instant.now().toString()
    val arbs = findArbs(betfair, paddy)
    val output = ArbOutput(
        computedAt = computedAt,
        betfairScrapedAt = betfair.scrapedAt,
        paddypowerScrapedAt = paddy.scrapedAt,
        arbCount = arbs.size,
        arbs = arbs,
    )
    File(paths.output).writeText(gson.toJson(output))
    println("Wrote ${paths.output} (${arbs.size} arbs from ${betfair.races.size} BF races and ${paddy.races.size} PP races)")
}

private fun readOrExit(path: String): String {
    val f = File(path)
    if (!f.exists()) {
        System.err.println("Error: input file not found: $path")
        kotlin.system.exitProcess(2)
    }
    return try {
        f.readText()
    } catch (e: Exception) {
        System.err.println("Error: failed to read $path: ${e.message}")
        kotlin.system.exitProcess(2)
    }
}
