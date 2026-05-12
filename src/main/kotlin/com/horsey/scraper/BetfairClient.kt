package com.horsey.scraper

import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

private const val LOGIN_URL     = "https://identitysso.betfair.com/api/login"
private const val CATALOGUE_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/"
private const val BOOK_URL      = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketBook/"

/**
 * Thin REST client for the three Betfair Exchange endpoints we use.
 *
 * Construct with the app key only. Call [login] once with username/password
 * — it stores the returned ssoid and uses it for every subsequent call.
 *
 * Errors:
 * - Login failures throw `IllegalStateException` (status surfaced).
 * - HTTP errors (non-2xx) throw `IllegalStateException` with the status code
 *   and the first 500 chars of the body.
 *
 * Retries: none. The caller decides what to drop on transient failures.
 */
class BetfairClient(
    private val appKey: String,
    private val http: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build(),
) {
    private var ssoid: String? = null

    fun login(username: String, password: String) {
        val req = HttpRequest.newBuilder()
            .uri(URI.create(LOGIN_URL))
            .timeout(Duration.ofSeconds(15))
            .header("X-Application", appKey)
            .header("Accept", "application/json")
            .header("Content-Type", "application/x-www-form-urlencoded")
            .POST(HttpRequest.BodyPublishers.ofString(buildLoginBody(username, password)))
            .build()
        val body = sendForBody(req)
        ssoid = parseSsoid(body)
    }

    fun listMarketCatalogue(body: String): String {
        val req = bettingRequest(CATALOGUE_URL, body)
        return sendForBody(req)
    }

    fun listMarketBook(body: String): String {
        val req = bettingRequest(BOOK_URL, body)
        return sendForBody(req)
    }

    private fun bettingRequest(url: String, body: String): HttpRequest {
        val token = ssoid ?: error("BetfairClient: must call login() before betting endpoints")
        return HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofSeconds(30))
            .header("X-Application", appKey)
            .header("X-Authentication", token)
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build()
    }

    private fun sendForBody(req: HttpRequest): String {
        val res: HttpResponse<String> = http.send(req, HttpResponse.BodyHandlers.ofString())
        if (res.statusCode() / 100 != 2) {
            val snip = res.body().take(500)
            error("HTTP ${res.statusCode()} from ${req.uri()}: $snip")
        }
        return res.body()
    }
}
