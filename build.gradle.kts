plugins {
    kotlin("jvm") version "1.9.21"
    application
}

group = "com.horsey.scraper"
version = "1.0-SNAPSHOT"

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.google.code.gson:gson:2.10.1")
    implementation("com.microsoft.playwright:playwright:1.47.0")

    testImplementation(kotlin("test"))
    // Gradle 9 requires explicit junit-platform-console for useJUnitPlatform() test task discovery
    testRuntimeOnly("org.junit.platform:junit-platform-console:1.9.3")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set(
        (project.findProperty("mainClass") as String?) ?: "com.horsey.scraper.MainKt"
    )
}

kotlin {
    jvmToolchain(17)
}
