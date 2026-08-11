package com.genrobotics.pockettts

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

class ModelManager(private val context: Context) {
    companion object {
        const val MODEL_NAME = "sherpa-onnx-pocket-tts-int8-2026-01-26"
        const val MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-pocket-tts-int8-2026-01-26.tar.bz2"
        private val REQUIRED = listOf(
            "lm_flow.int8.onnx",
            "lm_main.int8.onnx",
            "encoder.onnx",
            "decoder.int8.onnx",
            "text_conditioner.onnx",
            "vocab.json",
            "token_scores.json"
        )
    }

    val modelsRoot: File get() = File(context.filesDir, "models")
    val modelDir: File get() = File(modelsRoot, MODEL_NAME)
    val defaultVoice: File get() = File(modelDir, "test_wavs/bria.wav")

    fun isReady(): Boolean = REQUIRED.all { File(modelDir, it).isFile && File(modelDir, it).length() > 0 }
    fun missingFiles(): List<String> = REQUIRED.filterNot { File(modelDir, it).isFile && File(modelDir, it).length() > 0 }
    fun modelBytes(): Long = if (!modelDir.exists()) 0L else modelDir.walkTopDown().filter { it.isFile }.sumOf { it.length() }

    suspend fun downloadAndInstall(onProgress: (Int, String) -> Unit) = withContext(Dispatchers.IO) {
        modelsRoot.mkdirs()
        val archive = File(context.cacheDir, "$MODEL_NAME.tar.bz2")
        val partial = File(context.cacheDir, "$MODEL_NAME.tar.bz2.part")
        partial.delete()
        onProgress(0, "Connecting to official model release…")

        val connection = URL(MODEL_URL).openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = true
        connection.connectTimeout = 20_000
        connection.readTimeout = 60_000
        connection.setRequestProperty("User-Agent", "PocketTTSStudio/0.1 Android")
        connection.connect()
        if (connection.responseCode !in 200..299) throw IllegalStateException("Model download failed: HTTP ${connection.responseCode}")
        val total = connection.contentLengthLong
        connection.inputStream.use { raw ->
            BufferedInputStream(raw, 256 * 1024).use { input ->
                BufferedOutputStream(FileOutputStream(partial), 256 * 1024).use { output ->
                    val buffer = ByteArray(256 * 1024)
                    var read: Int
                    var done = 0L
                    var last = -1
                    while (input.read(buffer).also { read = it } >= 0) {
                        if (read == 0) continue
                        output.write(buffer, 0, read)
                        done += read
                        val p = if (total > 0) ((done * 82L) / total).toInt().coerceIn(0, 82) else 0
                        if (p != last) {
                            last = p
                            onProgress(p, "Downloading model ${formatBytes(done)}${if (total > 0) " / ${formatBytes(total)}" else ""}")
                        }
                    }
                }
            }
        }
        connection.disconnect()
        if (!partial.renameTo(archive)) {
            partial.copyTo(archive, overwrite = true)
            partial.delete()
        }

        onProgress(83, "Extracting PocketTTS model…")
        if (modelDir.exists()) modelDir.deleteRecursively()
        extractTarBz2(archive, modelsRoot) { index ->
            onProgress((83 + index.coerceAtMost(15)).coerceAtMost(98), "Installing model files…")
        }
        archive.delete()

        val missing = missingFiles()
        if (missing.isNotEmpty()) throw IllegalStateException("Model install incomplete: ${missing.joinToString()}")
        onProgress(100, "Model ready • ${formatBytes(modelBytes())}")
    }

    fun deleteModel() { modelDir.deleteRecursively() }

    private fun extractTarBz2(archive: File, destination: File, onStep: (Int) -> Unit) {
        val canonicalRoot = destination.canonicalFile
        FileInputStream(archive).use { fis ->
            BufferedInputStream(fis, 256 * 1024).use { bis ->
                BZip2CompressorInputStream(bis, true).use { bz ->
                    TarArchiveInputStream(bz).use { tar ->
                        var entry = tar.nextTarEntry
                        var count = 0
                        while (entry != null) {
                            val out = File(destination, entry.name).canonicalFile
                            if (!out.path.startsWith(canonicalRoot.path + File.separator)) throw SecurityException("Unsafe archive path: ${entry.name}")
                            if (entry.isDirectory) out.mkdirs() else {
                                out.parentFile?.mkdirs()
                                BufferedOutputStream(FileOutputStream(out), 256 * 1024).use { output -> tar.copyTo(output, 256 * 1024) }
                            }
                            count++
                            onStep(count)
                            entry = tar.nextTarEntry
                        }
                    }
                }
            }
        }
    }

    private fun formatBytes(v: Long): String {
        if (v < 1024) return "$v B"
        val kb = v / 1024.0
        if (kb < 1024) return String.format("%.1f KB", kb)
        return String.format("%.1f MB", kb / 1024.0)
    }
}
