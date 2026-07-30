package com.nekospeak.tts.data

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

data class ModelFile(
    val fileName: String,
    val downloadUrl: String,
    val description: String,
    val mirrors: List<String> = emptyList(),
    val minBytes: Long = 1024L
) {
    fun allUrls(): List<String> = (listOf(downloadUrl) + mirrors).distinct()
}

data class ModelInfo(
    val id: String,
    val name: String,
    val description: String,
    val files: List<ModelFile>,
    val version: String = "1.0"
)

object ModelRepository {
    private const val TAG = "ModelRepository"
    private const val USER_AGENT = "NekoSpeak-Studio/1.5 (Android)"
    private const val MAX_REDIRECTS = 10
    private const val MAX_ATTEMPTS_PER_URL = 3

    private const val POCKET_BASE = "https://huggingface.co/KevinAHM/pocket-tts-onnx/resolve/main"
    private const val POCKET_LEGACY = "https://huggingface.co/spaces/KevinAHM/pocket-tts-web/resolve/main"
    private const val VOICES_BASE = "https://huggingface.co/kyutai/tts-voices/resolve/main"
    private const val MAL_BASE = "https://huggingface.co/trysem/mms-tts-ml-ONNX/resolve/main"

    val models = listOf(
        ModelInfo(
            id = "pocket_v1",
            name = "Pocket-TTS Natural Voice Cloning",
            description = "Compact multilingual neural TTS with local zero-shot voice cloning (~200 MB).",
            version = "2026.04",
            files = listOf(
                ModelFile(
                    "pocket/models/mimi_encoder.onnx",
                    "$POCKET_BASE/onnx/mimi_encoder.onnx?download=true",
                    "Mimi voice encoder",
                    mirrors = listOf("$POCKET_LEGACY/onnx/mimi_encoder.onnx?download=true"),
                    minBytes = 10L * 1024L * 1024L
                ),
                ModelFile(
                    "pocket/models/text_conditioner.onnx",
                    "$POCKET_BASE/onnx/text_conditioner.onnx?download=true",
                    "Text conditioner",
                    mirrors = listOf("$POCKET_LEGACY/onnx/text_conditioner.onnx?download=true"),
                    minBytes = 5L * 1024L * 1024L
                ),
                ModelFile(
                    "pocket/models/flow_lm_main_int8.onnx",
                    "$POCKET_BASE/onnx/flow_lm_main_int8.onnx?download=true",
                    "Flow language model INT8",
                    mirrors = listOf("$POCKET_LEGACY/onnx/flow_lm_main_int8.onnx?download=true"),
                    minBytes = 20L * 1024L * 1024L
                ),
                ModelFile(
                    "pocket/models/flow_lm_flow_int8.onnx",
                    "$POCKET_BASE/onnx/flow_lm_flow_int8.onnx?download=true",
                    "Flow matching model INT8",
                    mirrors = listOf("$POCKET_LEGACY/onnx/flow_lm_flow_int8.onnx?download=true"),
                    minBytes = 2L * 1024L * 1024L
                ),
                ModelFile(
                    "pocket/models/mimi_decoder_int8.onnx",
                    "$POCKET_BASE/onnx/mimi_decoder_int8.onnx?download=true",
                    "Mimi audio decoder INT8",
                    mirrors = listOf("$POCKET_LEGACY/onnx/mimi_decoder_int8.onnx?download=true"),
                    minBytes = 5L * 1024L * 1024L
                ),
                ModelFile(
                    "pocket/tokenizer.model",
                    "$POCKET_BASE/tokenizer.model?download=true",
                    "SentencePiece tokenizer",
                    mirrors = listOf("$POCKET_LEGACY/tokenizer.model?download=true"),
                    minBytes = 20L * 1024L
                ),
                ModelFile("pocket/voices/alba.wav", "$VOICES_BASE/alba-mackenna/casual.wav?download=true", "Alba voice", minBytes = 20L * 1024L),
                ModelFile("pocket/voices/marius.wav", "$VOICES_BASE/voice-donations/Selfie.wav?download=true", "Marius voice", minBytes = 20L * 1024L),
                ModelFile("pocket/voices/javert.wav", "$VOICES_BASE/voice-donations/Butter.wav?download=true", "Javert voice", minBytes = 20L * 1024L),
                ModelFile("pocket/voices/jean.wav", "$VOICES_BASE/ears/p010/freeform_speech_01.wav?download=true", "Jean voice", minBytes = 20L * 1024L)
            )
        ),
        ModelInfo(
            id = "mms_malayalam",
            name = "Malayalam Natural (MMS-VITS)",
            description = "Offline Malayalam neural voice. Quantized ONNX model optimized for local Android inference.",
            version = "1.0",
            files = listOf(
                ModelFile(
                    "malayalam/model.onnx",
                    "$MAL_BASE/onnx/model_quantized.onnx?download=true",
                    "Malayalam VITS quantized model",
                    mirrors = listOf(
                        "$MAL_BASE/onnx/model_int8.onnx?download=true",
                        "$MAL_BASE/onnx/model_uint8.onnx?download=true",
                        "$MAL_BASE/onnx/model.onnx?download=true",
                        "$MAL_BASE/model.onnx?download=true"
                    ),
                    minBytes = 20L * 1024L * 1024L
                ),
                ModelFile("malayalam/vocab.json", "$MAL_BASE/vocab.json?download=true", "Malayalam vocabulary", minBytes = 256L),
                ModelFile("malayalam/tokenizer_config.json", "$MAL_BASE/tokenizer_config.json?download=true", "Tokenizer configuration", minBytes = 128L),
                ModelFile("malayalam/config.json", "$MAL_BASE/config.json?download=true", "Model configuration", minBytes = 256L)
            )
        ),
        ModelInfo(
            id = "kokoro_v1.0",
            name = "Kokoro v1.0",
            description = "High-quality expressive English voices.",
            files = listOf(
                ModelFile("kokoro-v1.0.int8.onnx", "https://github.com/siva-sub/NekoSpeak/releases/download/v1.0.0/kokoro-v1.0.int8.onnx", "Model weights", minBytes = 20L * 1024L * 1024L),
                ModelFile("voices-v1.0.bin", "https://github.com/siva-sub/NekoSpeak/releases/download/v1.0.0/voices-v1.0.bin", "Voice pack", minBytes = 1024L * 1024L)
            )
        ),
        ModelInfo(
            id = "kitten_nano",
            name = "Kitten TTS Nano",
            description = "Small low-latency English model.",
            files = listOf(
                ModelFile("kitten_tts_nano_v0_1.onnx", "https://github.com/siva-sub/NekoSpeak/releases/download/v1.0.0/kitten_tts_nano_v0_1.onnx", "Model weights", minBytes = 5L * 1024L * 1024L),
                ModelFile("voices.npz", "https://github.com/siva-sub/NekoSpeak/releases/download/v1.0.0/voices.npz", "Voice pack", minBytes = 100L * 1024L)
            )
        )
    )

    private val downloadStates = mutableMapOf<String, MutableStateFlow<Float>>()
    private val lastErrors = mutableMapOf<String, String>()

    fun getDownloadProgress(modelId: String): StateFlow<Float>? = downloadStates[modelId]?.asStateFlow()

    fun getLastError(modelId: String): String? = synchronized(lastErrors) { lastErrors[modelId] }

    fun isInstalled(context: Context, modelId: String): Boolean {
        val model = models.find { it.id == modelId } ?: return false
        return model.files.all { def ->
            val file = File(context.filesDir, def.fileName)
            file.exists() && file.length() >= def.minBytes
        }
    }

    suspend fun downloadModel(context: Context, modelId: String, onComplete: (Boolean) -> Unit) = withContext(Dispatchers.IO) {
        val model = models.find { it.id == modelId } ?: run {
            withContext(Dispatchers.Main) { onComplete(false) }
            return@withContext
        }

        synchronized(downloadStates) {
            if (downloadStates.containsKey(modelId)) return@withContext
            downloadStates[modelId] = MutableStateFlow(0f)
        }
        synchronized(lastErrors) { lastErrors.remove(modelId) }

        val progress = downloadStates.getValue(modelId)
        try {
            val totalFiles = model.files.size.coerceAtLeast(1)
            var completedFiles = 0
            for (fileDef in model.files) {
                val target = File(context.filesDir, fileDef.fileName)
                if (target.exists() && target.length() >= fileDef.minBytes) {
                    completedFiles++
                    progress.value = completedFiles.toFloat() / totalFiles
                    continue
                }
                target.parentFile?.mkdirs()

                val result = downloadWithMirrors(fileDef, target) { fileProgress ->
                    progress.value = (completedFiles + fileProgress.coerceIn(0f, 1f)) / totalFiles
                }
                if (!result.success) {
                    val message = "${fileDef.description}: ${result.error ?: "download failed"}"
                    synchronized(lastErrors) { lastErrors[modelId] = message }
                    Log.e(TAG, message)
                    withContext(Dispatchers.Main) { onComplete(false) }
                    return@withContext
                }
                completedFiles++
                progress.value = completedFiles.toFloat() / totalFiles
            }
            withContext(Dispatchers.Main) { onComplete(true) }
        } catch (t: Throwable) {
            val message = t.message ?: t::class.java.simpleName
            synchronized(lastErrors) { lastErrors[modelId] = message }
            Log.e(TAG, "Model download failed", t)
            withContext(Dispatchers.Main) { onComplete(false) }
        } finally {
            synchronized(downloadStates) { downloadStates.remove(modelId) }
        }
    }

    private data class DownloadResult(val success: Boolean, val error: String? = null)

    private suspend fun downloadWithMirrors(
        fileDef: ModelFile,
        target: File,
        onProgress: (Float) -> Unit
    ): DownloadResult {
        var lastError = "No download source succeeded"
        for (url in fileDef.allUrls()) {
            repeat(MAX_ATTEMPTS_PER_URL) { attempt ->
                val result = downloadResumable(url, target, fileDef.minBytes, onProgress)
                if (result.success) return result
                lastError = result.error ?: lastError
                if (attempt < MAX_ATTEMPTS_PER_URL - 1) {
                    delay(1500L * (attempt + 1))
                }
            }
        }
        return DownloadResult(false, lastError)
    }

    private fun downloadResumable(
        initialUrl: String,
        target: File,
        minBytes: Long,
        onProgress: (Float) -> Unit
    ): DownloadResult {
        val partial = File(target.absolutePath + ".part")
        var connection: HttpURLConnection? = null
        return try {
            var currentUrl = initialUrl
            var redirects = 0
            val existingBytes = partial.takeIf { it.exists() }?.length() ?: 0L

            while (true) {
                val url = URL(currentUrl)
                connection = (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 30_000
                    readTimeout = 300_000
                    requestMethod = "GET"
                    setRequestProperty("User-Agent", USER_AGENT)
                    setRequestProperty("Accept", "application/octet-stream,*/*")
                    if (existingBytes > 0L) setRequestProperty("Range", "bytes=$existingBytes-")
                    instanceFollowRedirects = false
                }

                val code = connection.responseCode
                if (code in listOf(301, 302, 303, 307, 308)) {
                    if (++redirects > MAX_REDIRECTS) return DownloadResult(false, "too many redirects")
                    val location = connection.getHeaderField("Location")
                        ?: return DownloadResult(false, "redirect did not include a Location header")
                    currentUrl = URL(url, location).toString()
                    connection.disconnect()
                    connection = null
                    continue
                }

                if (code != HttpURLConnection.HTTP_OK && code != HttpURLConnection.HTTP_PARTIAL) {
                    return DownloadResult(false, "HTTP $code from ${url.host}")
                }

                val append = code == HttpURLConnection.HTTP_PARTIAL && existingBytes > 0L
                if (!append && partial.exists()) partial.delete()
                val start = if (append) existingBytes else 0L
                val remaining = connection.contentLengthLong
                val expectedTotal = if (remaining > 0L) start + remaining else -1L
                var downloaded = start

                connection.inputStream.use { input ->
                    FileOutputStream(partial, append).use { output ->
                        val buffer = ByteArray(128 * 1024)
                        while (true) {
                            val read = input.read(buffer)
                            if (read < 0) break
                            output.write(buffer, 0, read)
                            downloaded += read
                            if (expectedTotal > 0L) onProgress(downloaded.toFloat() / expectedTotal)
                        }
                        output.fd.sync()
                    }
                }

                if (partial.length() < minBytes) {
                    return DownloadResult(false, "received only ${partial.length()} bytes")
                }
                if (target.exists() && !target.delete()) {
                    return DownloadResult(false, "could not replace the existing file")
                }
                if (!partial.renameTo(target)) {
                    partial.copyTo(target, overwrite = true)
                    partial.delete()
                }
                onProgress(1f)
                return DownloadResult(true)
            }
        } catch (t: Throwable) {
            DownloadResult(false, t.message ?: t::class.java.simpleName)
        } finally {
            connection?.disconnect()
        }
    }

    fun deleteModel(context: Context, modelId: String) {
        val model = models.find { it.id == modelId } ?: return
        model.files.forEach { def ->
            File(context.filesDir, def.fileName).delete()
            File(context.filesDir, def.fileName + ".part").delete()
        }
        synchronized(lastErrors) { lastErrors.remove(modelId) }
    }
}
