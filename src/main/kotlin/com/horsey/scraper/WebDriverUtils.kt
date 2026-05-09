package com.horsey.scraper

import org.openqa.selenium.PageLoadStrategy
import org.openqa.selenium.WebDriver
import org.openqa.selenium.chrome.ChromeDriver
import org.openqa.selenium.chrome.ChromeOptions
import java.time.Duration

/**
 * Creates a headless Chrome WebDriver configured for Betfair scraping.
 *
 * @return A new ChromeDriver — caller is responsible for calling quit().
 */
fun createChromeDriver(): WebDriver {
    val options = ChromeOptions().apply {
        addArguments("--headless=new")
        addArguments("--no-sandbox")
        addArguments("--disable-dev-shm-usage")
        addArguments("--disable-gpu")
        addArguments("--window-size=1920,1080")
        addArguments("--disable-blink-features=AutomationControlled")
        addArguments("--disable-extensions")
        addArguments("--disable-infobars")
        addArguments("--remote-allow-origins=*")
        addArguments("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        setExperimentalOption("excludeSwitches", listOf("enable-automation"))
        setExperimentalOption("useAutomationExtension", false)
        // Betfair pages keep loading trackers/pixels long after the race UI is
        // interactive. With the default "normal" strategy, driver.get() blocks
        // until window.onload — which on a slow Betfair page often exceeds the
        // 5-minute pageLoad timeout. Eager returns once DOMContentLoaded fires;
        // we then wait explicitly for the runners to appear.
        setPageLoadStrategy(PageLoadStrategy.EAGER)
    }
    val driver = ChromeDriver(options)
    driver.manage().timeouts().pageLoadTimeout(Duration.ofSeconds(60))
    return driver
}
