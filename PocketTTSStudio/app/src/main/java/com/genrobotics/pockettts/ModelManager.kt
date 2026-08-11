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
        private val POCKET_REQUIRED = listOf(
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
    val pocketPack: ModelPack get() = ModelCatalog.byId("pocket_en")
    val modelDir: File get() = dir(pocketPack)
    val defaultVoice: File get() = defaultVoice(pocketPack)

    fun dir(pack: ModelPack): File = File(modelsRoot, pack.dirName)

    fun defaultVoice(pack: ModelPack): File =
        if (pack.engine == EngineKind.POCKET) File(dir(pack), "test_wavs/bria.wav") else File("")

    fun isReady(): Boolean = isReady(pocketPack)

    fun isReady(pack: ModelPack): Boolean {
        val root = dir(pack)
        if (!root.isDirectory) return false
        return when (pack.engine) {
            EngineKind.POCKET -> POCKET_REQUIRED.all { File(root, it).isFile && File(root, it).length() > 0 }
            EngineKind.PIPER -> {
                File(root, pack.modelFile).let { it.isFile && it.length() > 0 } &&
                    File(root, "tokens.txt").let { it.isFile && it.length() > 0 } &&
                    File(root, "espeak-ng-data").isDirectory
            }
        }
    }

    fun missingFiles(pack: ModelPack): List<String> {
        val root = dir(pack)
        return when (pack.engine) {
            EngineKind.POCKET -> POCKET_REQUIRED.filterNot { File(root, it).isFile && File(root, it).length() > 0 }
            EngineKind.PIPER -> buildList {
                if (!File(root, pack.modelFile).isFile) add(pack.modelFile)
                if (!File(root, "tokens.txt").isFile) add("tokens.txt")
                if (!File(root, "espeak-ng-data").isDirectory) add("espeak-ng-data/")
            }
        }
    }

    fun modelBytes(): Long = modelBytes(pocketPack)

    fun modelBytes(pack: ModelPack): Long {
        val root = dir(pack)
        return if (!root.exists()) 0L else root.walkTopDown().filter { it.isFile }.sumOf { it.length() }
    }

    fun installedPacks(): List<ModelPack> = ModelCatalog.packs.filter { isReady(it) }
    fun totalInstalledBytes(): Long = installedPacks().sumOf { modelBytes(it) }

    suspend fun downloadAndInstall(onProgress: (Int, String) -> Unit) = install(pocketPack, onProgress)

    suspend fun install(pack: ModelPack, onProgress: (Int, String) -> Unit) = withContext(Dispatchers.IO) {
        modelsRoot.mkdirs()
        val archive = File(context.cacheDir, "${pack.dirName}.tar.bz2")
        val partial = File(context.cacheDir, "${pack.dirName}.tar.bz2.part")
        partial.delete()
        archive.delete()
        onProgress(0, "Connecting • ${pack.displayName}")

        val connection = URL(pack.archiveUrl).openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = true
        connection.connectTimeout = 25_000
        connection.readTimeout = 90_000
        connection.setRequestProperty("User-Agent", "PocketTTS-Ultra-Studio/0.2 Android")
        connection.connect()
        if (connection.responseCode !in 200..299) {
            connection.disconnect()
            throw IllegalStateException("Model download failed: HTTP ${connection.responseCode}")
        }

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
                        val p = if (total > 0) ((done * 84L) / total).toInt().coerceIn(0, 84) else 1
                        if (p != last) {
                            last = p
                            onProgress(
                                p,
                                "Downloading ${pack.voiceName} • ${formatBytes(done)}${if (total > 0) " / ${formatBytes(total)}" else ""}"
                            )
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
        require(archive.isFile && archive.length() > 0) { "Downloaded archive is empty" }

        onProgress(85, "Extracting ${pack.displayName}…")
        val target = dir(pack)
        if (target.exists()) target.deleteRecursively()
        extractTarBz2(archive, modelsRoot) { count ->
            onProgress((85 + count.coerceAtMost(13)).coerceAtMost(98), "Installing model files…")
        }
        archive.delete()

        val missing = missingFiles(pack)
        if (missing.isNotEmpty()) {
            target.deleteRecursively()
            throw IllegalStateException("Install validation failed: ${missing.joinToString()}")
        }
        onProgress(100, "Installed • ${pack.displayName} • ${formatBytes(modelBytes(pack))}")
    }

    fun deleteModel() = delete(pocketPack)
    fun delete(pack: ModelPack) { dir(pack).deleteRecursively() }

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
                            if (!out.path.startsWith(canonicalRoot.path + File.separator)) {
                                throw SecurityException("Unsafe archive path: ${entry.name}")
                            }
                            if (entry.isDirectory) {
                                out.mkdirs()
                            } else {
                                out.parentFile?.mkdirs()
                                BufferedOutputStream(FileOutputStream(out), 256 * 1024).use { output ->
                                    tar.copyTo(output, 256 * 1024)
                                }
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

    fun formatBytes(v: Long): String {
        if (v < 1024) return "$v B"
        val kb = v / 1024.0
        if (kb < 1024) return String.format("%.1f KB", kb)
        val mb = kb / 1024.0
        if (mb < 1024) return String.format("%.1f MB", mb)
        return String.format("%.2f GB", mb / 1024.0)
    }
}
