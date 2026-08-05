from pathlib import Path

ROOT = Path("build-src/CareerPilotAI")


def replace_exact(path: str, old: str, new: str, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} occurrence(s), found {actual}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace_exact(
    "app/src/main/java/com/careerpilot/ai/data/AppDatabase.kt",
    "exportSchema = true",
    "exportSchema = false",
)

replace_exact(
    "app/src/main/java/com/careerpilot/ai/discovery/JobDiscovery.kt",
    "abstract class JsonJobConnector(protected val client: OkHttpClient) : JobDiscoveryConnector {",
    "abstract class JsonJobConnector(protected val client: OkHttpClient) {",
)
for connector in ("GreenhouseConnector", "LeverConnector", "AshbyConnector"):
    replace_exact(
        "app/src/main/java/com/careerpilot/ai/discovery/JobDiscovery.kt",
        f"class {connector}(client: OkHttpClient) : JsonJobConnector(client) {{",
        f"class {connector}(client: OkHttpClient) : JsonJobConnector(client), JobDiscoveryConnector {{",
    )

old_brave = '''        return root.obj("web").array("results").mapNotNull { resultElement ->
            val result = resultElement.jsonObject
            val url = result.string("url")
            if (url.isBlank()) return@mapNotNull null
            runCatching { importer.import(url) }.getOrElse {
                val domain = runCatching { URI(url).host.removePrefix("www.") }.getOrDefault("Web listing")
                DiscoveredJob(
                    externalId = url,
                    title = cleanHtml(result.string("title")).replace(Regex("\\\\s+[|–-]\\\\s+.*$"), ""),
                    company = domain,
                    location = settings.location,
                    url = url,
                    description = cleanHtml(result.string("description"))
                )
            }
        }.distinctBy { it.url }'''
new_brave = '''        val discovered = mutableListOf<DiscoveredJob>()
        for (resultElement in root.obj("web").array("results")) {
            val result = resultElement.jsonObject
            val url = result.string("url")
            if (url.isBlank()) continue
            val job = try {
                importer.import(url)
            } catch (_: Throwable) {
                val domain = runCatching { URI(url).host.removePrefix("www.") }.getOrDefault("Web listing")
                DiscoveredJob(
                    externalId = url,
                    title = cleanHtml(result.string("title")).replace(Regex("\\\\s+[|–-]\\\\s+.*$"), ""),
                    company = domain,
                    location = settings.location,
                    url = url,
                    description = cleanHtml(result.string("description"))
                )
            }
            discovered += job
        }
        return discovered.distinctBy { it.url }'''
replace_exact("app/src/main/java/com/careerpilot/ai/discovery/JobDiscovery.kt", old_brave, new_brave)

replace_exact(
    "app/src/main/java/com/careerpilot/ai/ui/AppViewModel.kt",
    "replaceFirstChar(Char::titlecase)",
    "replaceFirstChar { it.uppercase() }",
    count=2,
)

old_typography = '''private val CareerTypography = Typography(
    displaySmall = TextStyle(FontFamily.SansSerif, FontWeight.Black, 34.sp, lineHeight = 39.sp, letterSpacing = (-0.8).sp),
    headlineLarge = TextStyle(FontFamily.SansSerif, FontWeight.Black, 29.sp, lineHeight = 34.sp, letterSpacing = (-0.5).sp),
    headlineMedium = TextStyle(FontFamily.SansSerif, FontWeight.ExtraBold, 24.sp, lineHeight = 29.sp),
    headlineSmall = TextStyle(FontFamily.SansSerif, FontWeight.Bold, 21.sp, lineHeight = 26.sp),
    titleLarge = TextStyle(FontFamily.SansSerif, FontWeight.Bold, 19.sp, lineHeight = 24.sp),
    titleMedium = TextStyle(FontFamily.SansSerif, FontWeight.SemiBold, 16.sp, lineHeight = 21.sp),
    bodyLarge = TextStyle(FontFamily.SansSerif, FontWeight.Normal, 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(FontFamily.SansSerif, FontWeight.Normal, 14.sp, lineHeight = 21.sp),
    labelLarge = TextStyle(FontFamily.SansSerif, FontWeight.Bold, 14.sp, lineHeight = 18.sp),
    labelMedium = TextStyle(FontFamily.SansSerif, FontWeight.SemiBold, 12.sp, lineHeight = 16.sp)
)'''
new_typography = '''private val CareerTypography = Typography(
    displaySmall = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Black, fontSize = 34.sp, lineHeight = 39.sp, letterSpacing = (-0.8).sp),
    headlineLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Black, fontSize = 29.sp, lineHeight = 34.sp, letterSpacing = (-0.5).sp),
    headlineMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.ExtraBold, fontSize = 24.sp, lineHeight = 29.sp),
    headlineSmall = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold, fontSize = 21.sp, lineHeight = 26.sp),
    titleLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold, fontSize = 19.sp, lineHeight = 24.sp),
    titleMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 21.sp),
    bodyLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 21.sp),
    labelLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold, fontSize = 14.sp, lineHeight = 18.sp),
    labelMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, lineHeight = 16.sp)
)'''
replace_exact("app/src/main/java/com/careerpilot/ai/ui/theme/Theme.kt", old_typography, new_typography)

replace_exact(
    "gradle.properties",
    "org.gradle.jvmargs=-Xmx4g -Dfile.encoding=UTF-8",
    "org.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1536m -Dfile.encoding=UTF-8",
)

print("CareerPilot Pro 2 compiler fixes applied successfully")
