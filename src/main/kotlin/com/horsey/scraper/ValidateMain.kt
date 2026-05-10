package com.horsey.scraper

import java.io.File
import kotlin.system.exitProcess

/**
 * Entry point: validate a data.json file against the spec.
 *
 * Usage:
 *   ./gradlew run -PmainClass=com.horsey.scraper.ValidateMainKt --args='data.json'
 *
 * Exits with code 0 if valid, 1 if validation errors found, 2 on file error.
 */
fun main(args: Array<String>) {
    val path = args.firstOrNull() ?: "data.json"
    val file = File(path)
    if (!file.exists()) {
        System.err.println("File not found: $path")
        exitProcess(2)
    }
    val errors = validateScrapeOutput(file.readText())
    if (errors.isEmpty()) {
        println("$path: VALID (matches spec)")
        exitProcess(0)
    } else {
        println("$path: INVALID (${errors.size} errors)")
        errors.forEach { println("  - $it") }
        exitProcess(1)
    }
}
