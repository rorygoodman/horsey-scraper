package com.horsey.scraper

import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.LinkedBlockingQueue

/**
 * Scrapes a list of races concurrently using `workerCount` threads pulling
 * from a shared queue. Returns successful (`RaceOdds`-non-null) results
 * sorted by `(offTime, venue)`.
 *
 *  - Each worker loops: `poll()` → if null, exit; else call `scrapeRace`,
 *    invoke `onResult`, sleep `perWorkerDelayMs` before the next pull.
 *    The first race on each worker has no leading delay; the last has no
 *    trailing delay.
 *  - `scrapeRace` may return null (race dropped) or throw. Both are caught
 *    inside the worker, reported via `onResult(workerId, race, null)`, and
 *    excluded from the returned list. Other races and other workers are
 *    unaffected.
 *  - `onResult` is invoked exactly once per race (success, drop, or throw).
 *    `println` is line-atomic on the JVM, so a logging `onResult` produces
 *    interleaved-but-readable output.
 *  - If `workerCount > races.size`, surplus workers exit immediately on
 *    first empty `poll()`. Harmless.
 *  - If `races` is empty, returns empty list immediately (workers still
 *    start and exit cleanly).
 */
fun scrapeRacesInParallel(
    races: List<Race>,
    workerCount: Int,
    perWorkerDelayMs: Long,
    scrapeRace: (Race) -> RaceOdds?,
    onResult: (workerId: Int, race: Race, odds: RaceOdds?) -> Unit
): List<RaceOdds> {
    val queue = LinkedBlockingQueue(races)
    val results = ConcurrentLinkedQueue<RaceOdds>()

    val threads = (0 until workerCount).map { workerId ->
        Thread({
            var first = true
            while (true) {
                val race = queue.poll() ?: break
                if (!first) Thread.sleep(perWorkerDelayMs)
                first = false

                val odds: RaceOdds? = try {
                    scrapeRace(race)
                } catch (e: Exception) {
                    System.err.println("[w$workerId] ${race.raceId} threw: ${e.javaClass.simpleName}: ${e.message}")
                    null
                }
                onResult(workerId, race, odds)
                if (odds != null) results.add(odds)
            }
        }, "horsey-worker-$workerId").apply {
            uncaughtExceptionHandler = Thread.UncaughtExceptionHandler { t, e ->
                System.err.println("Worker thread ${t.name} died: ${e.javaClass.simpleName}: ${e.message}")
            }
            start()
        }
    }
    threads.forEach { it.join() }

    return results.toList().sortedWith(compareBy({ it.offTime }, { it.venue }))
}
