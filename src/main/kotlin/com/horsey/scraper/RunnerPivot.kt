package com.horsey.scraper

/**
 * Combines per-market scrapes into a per-runner pivot.
 *
 * Rules (see spec, "Edge-case rules"):
 *   - WIN absent → returns empty list (no runner source of truth).
 *   - Each runner's lay map has exactly the keys present in `scrapes`.
 *   - Runner not seen in some scraped market → that key maps to null.
 *   - Runner appearing in Top-N but not WIN → dropped, stderr warning.
 *   - Result preserves MarketType declared order in each runner's lay map
 *     and Win-page order in the runners list.
 */
fun pivotMarketScrapes(
    scrapes: Map<MarketType, MarketScrape>,
    raceIdForWarnings: String
): List<RunnerOdds> {
    val win = scrapes[MarketType.WIN] ?: return emptyList()

    val winNames: Set<String> = win.runners.map { it.name }.toSet()
    val orderedTypes = MarketType.values().filter { it in scrapes }

    // Phantom-horse warnings: anyone in a scraped Top-N market but not in WIN.
    for (type in orderedTypes) {
        if (type == MarketType.WIN) continue
        for (entry in scrapes.getValue(type).runners) {
            if (entry.name !in winNames) {
                System.err.println("Phantom horse '${entry.name}' in $type for race $raceIdForWarnings — dropping")
            }
        }
    }

    return win.runners.map { winEntry ->
        val lay = linkedMapOf<MarketType, Double?>()
        for (type in orderedTypes) {
            val market = scrapes.getValue(type)
            // Find this horse's entry in this market (null if absent or no offer).
            val entry = market.runners.firstOrNull { it.name == winEntry.name }
            lay[type] = entry?.lay
        }
        RunnerOdds(name = winEntry.name, lay = lay, selectionId = winEntry.selectionId)
    }
}
