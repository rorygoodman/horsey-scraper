package com.horsey.scraper

/**
 * Known UK and Irish racecourses, used to filter the Betfair race list to
 * GB/IE meetings.
 *
 * Names match the Betfair display name. When Betfair adds a new course or
 * spells one differently, update this list.
 */
object Venues {
    val UK = setOf(
        "Aintree", "Ascot", "Ayr", "Bangor", "Bath", "Beverley", "Brighton",
        "Carlisle", "Cartmel", "Catterick", "Chelmsford", "Cheltenham",
        "Chepstow", "Chester", "Doncaster", "Epsom", "Exeter", "Fakenham",
        "Ffos Las", "Fontwell", "Goodwood", "Hamilton", "Haydock", "Hereford",
        "Hexham", "Huntingdon", "Kelso", "Kempton", "Leicester", "Lingfield",
        "Ludlow", "Market Rasen", "Musselburgh", "Newbury", "Newcastle",
        "Newmarket", "Newton Abbot", "Nottingham", "Perth", "Plumpton",
        "Pontefract", "Redcar", "Ripon", "Salisbury", "Sandown", "Sedgefield",
        "Southwell", "Stratford", "Taunton", "Thirsk", "Uttoxeter", "Warwick",
        "Wetherby", "Wincanton", "Windsor", "Wolverhampton", "Worcester",
        "Yarmouth", "York"
    )

    val IE = setOf(
        "Ballinrobe", "Bellewstown", "Clonmel", "Cork", "Curragh", "Down Royal",
        "Downpatrick", "Dundalk", "Fairyhouse", "Galway", "Gowran Park",
        "Kilbeggan", "Killarney", "Laytown", "Leopardstown", "Limerick",
        "Listowel", "Naas", "Navan", "Punchestown", "Roscommon", "Sligo",
        "Thurles", "Tipperary", "Tramore", "Wexford"
    )

    val ALL = UK + IE

    fun countryFor(venue: String): String? = when {
        UK.contains(venue) -> "GB"
        IE.contains(venue) -> "IE"
        else -> null
    }
}
