package com.horsey.scraper.arb

import java.io.File

/**
 * Entry point for ad-hoc validation:
 *   ./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbValidateMainKt --args=arbs.json
 */
fun main(args: Array<String>) {
    require(args.size == 1) { "usage: ArbValidateMain <path-to-arbs.json>" }
    val path = args[0]
    val errors = validateArbsOutput(File(path).readText())
    if (errors.isEmpty()) {
        println("$path: VALID (matches spec)")
    } else {
        System.err.println("$path: ${errors.size} errors")
        errors.forEach { System.err.println("  - $it") }
        kotlin.system.exitProcess(1)
    }
}
