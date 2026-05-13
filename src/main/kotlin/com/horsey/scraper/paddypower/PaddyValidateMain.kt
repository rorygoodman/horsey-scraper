package com.horsey.scraper.paddypower

import java.io.File

/**
 * Entry point for ad-hoc validation:
 *   ./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args=paddypower.json
 */
fun main(args: Array<String>) {
    require(args.size == 1) { "usage: PaddyValidateMain <path-to-paddypower.json>" }
    val path = args[0]
    val errors = validatePaddyOutput(File(path).readText())
    if (errors.isEmpty()) {
        println("$path: VALID (matches spec)")
    } else {
        System.err.println("$path: ${errors.size} errors")
        errors.forEach { System.err.println("  - $it") }
        kotlin.system.exitProcess(1)
    }
}
