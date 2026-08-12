package com.genrobotics.pockettts

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.URL
import javax.net.ssl.HttpsURLConnection


data class AuraNexusResult(
    val title: String,
    val summary: String,
    val scriptText: String,
    val characters: List<String>,
    val modelUsed: String,
    val rawJson: String
)

class AuraNimClient {
    private val endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"
    private val modelRing = listOf(
        "nvidia/nemotron-3.5-nano-30b-a3b",
        "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "meta/llama-3.3-70b-instruct"
    )

    @Volatile
    private var cancelled = false

    fun cancel() {
        cancelled = true
    }

    fun generate(apiKey: String, prompt: String): AuraNexusResult {
        require(apiKey.isNotBlank()) { "Enter an NVIDIA API key" }
        require(prompt.isNotBlank()) { "Enter a creative brief" }
        cancelled = false
        var lastError: Throwable? = null

        repeat(3) { round ->
            for (model in modelRing) {
                if (cancelled) throw IllegalStateException("Nexus generation cancelled")
                try {
                    val response = callModel(apiKey.trim(), model, prompt)
                    return parseResult(response, model)
                } catch (t: RetryableNimException) {
                    lastError = t
                    // Immediate model switch. Backoff only after a complete ring.
                } catch (t: Throwable) {
                    lastError = t
                    if (t is IllegalArgumentException) throw t
                }
            }
            if (round < 2) Thread.sleep((250L shl round).coerceAtMost(1200L))
        }
        throw IllegalStateException("All NVIDIA NIM models failed: ${lastError?.message ?: "unknown error"}")
    }

    private fun callModel(apiKey: String, model: String, prompt: String): String {
        val system = """
            You are AuraVox Studio's screenplay architect and casting director.
            Return JSON only. Design a production-ready multilingual voice script.
            JSON schema:
            {
              "title": "string",
              "summary": "string",
              "characters": ["Name — role/voice direction"],
              "script_text": "full readable script with speaker labels, scene breaks, emotion cues and pause cues"
            }
            Prefer Malayalam wording when the user asks for Malayalam. Preserve English-Malayalam code switching naturally.
            Do not invent voice-cloning consent or local file paths. Do not wrap the JSON in markdown.
        """.trimIndent()

        val messages = JSONArray()
            .put(JSONObject().put("role", "system").put("content", system))
            .put(JSONObject().put("role", "user").put("content", prompt))

        val body = JSONObject()
            .put("model", model)
            .put("messages", messages)
            .put("temperature", 0.45)
            .put("max_tokens", 6000)
            .put("stream", false)
            .toString()

        val connection = (URL(endpoint).openConnection() as HttpsURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 7000
            readTimeout = 75000
            doOutput = true
            useCaches = false
            setRequestProperty("Authorization", "Bearer $apiKey")
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "AuraVox-Android/0.3")
        }

        try {
            connection.outputStream.use { out -> out.write(body.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = if (stream != null) {
                BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
            } else ""

            if (code == 429 || code == 408 || code in 500..599) {
                throw RetryableNimException("$model returned HTTP $code")
            }
            if (code !in 200..299) {
                val message = runCatching {
                    JSONObject(text).optJSONObject("error")?.optString("message")
                }.getOrNull().orEmpty()
                throw IllegalStateException("NVIDIA HTTP $code${if (message.isNotBlank()) ": $message" else ""}")
            }

            val root = JSONObject(text)
            return root.getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .getString("content")
        } finally {
            connection.disconnect()
        }
    }

    private fun parseResult(content: String, model: String): AuraNexusResult {
        var cleaned = content.trim()
        if (cleaned.startsWith("```")) {
            cleaned = cleaned.removePrefix("```json").removePrefix("```").trim()
            if (cleaned.endsWith("```")) cleaned = cleaned.dropLast(3).trim()
        }
        val start = cleaned.indexOf('{')
        val end = cleaned.lastIndexOf('}')
        if (start >= 0 && end > start) cleaned = cleaned.substring(start, end + 1)

        val json = JSONObject(cleaned)
        val chars = mutableListOf<String>()
        val array = json.optJSONArray("characters") ?: JSONArray()
        for (i in 0 until array.length()) chars += array.optString(i)

        return AuraNexusResult(
            title = json.optString("title", "AuraVox Project"),
            summary = json.optString("summary", ""),
            scriptText = json.optString("script_text", cleaned),
            characters = chars,
            modelUsed = model,
            rawJson = cleaned
        )
    }

    private class RetryableNimException(message: String) : RuntimeException(message)
}
