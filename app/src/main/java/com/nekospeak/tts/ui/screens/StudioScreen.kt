package com.nekospeak.tts.ui.screens

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.os.PowerManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.nekospeak.tts.data.PrefsManager
import com.nekospeak.tts.engine.EngineFactory
import com.nekospeak.tts.studio.AudioFileExporter
import com.nekospeak.tts.studio.StudioAudioFormat
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private data class StudioChunk(val text: String, val paragraphEnd: Boolean)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudioScreen() {
    val context = LocalContext.current
    val view = LocalView.current
    val prefs = remember { PrefsManager(context) }
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }

    var text by rememberSaveable { mutableStateOf("") }
    var speed by rememberSaveable { mutableFloatStateOf(1.0f) }
    var sentencePauseMs by rememberSaveable { mutableFloatStateOf(180f) }
    var paragraphPauseMs by rememberSaveable { mutableFloatStateOf(520f) }
    var normalize by rememberSaveable { mutableStateOf(true) }
    var trimSilence by rememberSaveable { mutableStateOf(true) }
    var format by rememberSaveable { mutableStateOf(StudioAudioFormat.AAC) }
    var bitrate by rememberSaveable { mutableIntStateOf(64) }
    var progress by remember { mutableFloatStateOf(0f) }
    var status by remember { mutableStateOf("Ready") }
    var generating by remember { mutableStateOf(false) }
    var outputUri by remember { mutableStateOf<android.net.Uri?>(null) }

    var pocketTemp by rememberSaveable { mutableFloatStateOf(prefs.pocketTemperature) }
    var pocketSteps by rememberSaveable { mutableIntStateOf(prefs.pocketLsdSteps) }
    val sharedPrefs = remember { context.getSharedPreferences("nekospeak_prefs", Context.MODE_PRIVATE) }
    var malNoise by rememberSaveable { mutableFloatStateOf(sharedPrefs.getFloat("malayalam_noise_scale", 0.667f)) }
    var malDurationNoise by rememberSaveable { mutableFloatStateOf(sharedPrefs.getFloat("malayalam_duration_noise", 0.8f)) }

    val importText = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            runCatching {
                context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { reader ->
                    text = reader.readText()
                }
            }.onFailure { scope.launch { snackbar.showSnackbar("Unable to open text file: ${it.message}") } }
        }
    }

    DisposableEffect(generating) {
        view.keepScreenOn = generating
        onDispose { view.keepScreenOn = false }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = { TopAppBar(title = { Text("Long-form TTS Studio") }) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Text(
                "Active model: ${displayModelName(prefs.currentModel)}",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary
            )

            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                label = { Text("Text, article, chapter, or book section") },
                supportingText = {
                    Text("${text.length} characters • approximately ${estimateMinutes(text, speed)} minutes")
                },
                minLines = 9,
                maxLines = 20,
                enabled = !generating,
                modifier = Modifier.fillMaxWidth()
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { importText.launch(arrayOf("text/plain", "text/markdown", "application/octet-stream")) }, enabled = !generating) {
                    Icon(Icons.Default.FolderOpen, null)
                    Spacer(Modifier.width(6.dp))
                    Text("Import TXT/MD")
                }
                OutlinedButton(onClick = { text = "" }, enabled = text.isNotEmpty() && !generating) {
                    Text("Clear")
                }
            }

            HorizontalDivider()
            Text("Voice controls", fontWeight = FontWeight.Bold)
            LabeledSlider("Speech speed", speed, 0.5f..2.0f, "${"%.2f".format(speed)}×") { speed = it }
            LabeledSlider("Sentence pause", sentencePauseMs, 0f..1000f, "${sentencePauseMs.roundToInt()} ms") { sentencePauseMs = it }
            LabeledSlider("Paragraph pause", paragraphPauseMs, 0f..2000f, "${paragraphPauseMs.roundToInt()} ms") { paragraphPauseMs = it }

            if (prefs.currentModel == "pocket_v1") {
                Text("Pocket-TTS advanced", fontWeight = FontWeight.SemiBold)
                LabeledSlider("Temperature", pocketTemp, 0.3f..1.2f, "${"%.2f".format(pocketTemp)}") {
                    pocketTemp = it
                    prefs.pocketTemperature = it
                }
                Text("Flow matching steps", style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(1, 4, 6, 10).forEach { steps ->
                        FilterChip(
                            selected = pocketSteps == steps,
                            onClick = { pocketSteps = steps; prefs.pocketLsdSteps = steps },
                            label = { Text(steps.toString()) }
                        )
                    }
                }
            }

            if (prefs.currentModel == "mms_malayalam") {
                Text("Malayalam naturalness", fontWeight = FontWeight.SemiBold)
                LabeledSlider("Voice variation", malNoise, 0.2f..1.1f, "${"%.2f".format(malNoise)}") {
                    malNoise = it
                    sharedPrefs.edit().putFloat("malayalam_noise_scale", it).apply()
                }
                LabeledSlider("Rhythm variation", malDurationNoise, 0.2f..1.3f, "${"%.2f".format(malDurationNoise)}") {
                    malDurationNoise = it
                    sharedPrefs.edit().putFloat("malayalam_duration_noise", it).apply()
                }
                Text(
                    "Malayalam text is processed directly in Malayalam script. For best pronunciation, use Malayalam punctuation and spell out unusual abbreviations.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(checked = normalize, onCheckedChange = { normalize = it }, enabled = !generating)
                Spacer(Modifier.width(8.dp))
                Text("Loudness normalization")
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(checked = trimSilence, onCheckedChange = { trimSilence = it }, enabled = !generating)
                Spacer(Modifier.width(8.dp))
                Text("Trim excessive silence per segment")
            }

            HorizontalDivider()
            Text("Output", fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StudioAudioFormat.entries.forEach { item ->
                    FilterChip(
                        selected = format == item,
                        onClick = { format = item },
                        label = { Text(when (item) {
                            StudioAudioFormat.WAV -> "WAV lossless"
                            StudioAudioFormat.AAC -> "M4A / AAC"
                            StudioAudioFormat.OPUS -> "OGG / Opus"
                        }) },
                        enabled = !generating
                    )
                }
            }
            if (format != StudioAudioFormat.WAV) {
                Text("Compression bitrate")
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf(32, 48, 64, 96, 128).forEach { value ->
                        FilterChip(
                            selected = bitrate == value,
                            onClick = { bitrate = value },
                            label = { Text("$value kbps") },
                            enabled = !generating
                        )
                    }
                }
            }

            if (generating) {
                LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
                Text(status, style = MaterialTheme.typography.bodySmall)
            }

            Button(
                onClick = {
                    scope.launch {
                        generating = true
                        outputUri = null
                        progress = 0f
                        status = "Preparing model…"
                        val wakeLock = (context.getSystemService(Context.POWER_SERVICE) as PowerManager)
                            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "NekoSpeakStudio:LongForm")
                        wakeLock.acquire(60L * 60L * 1000L)
                        try {
                            val uri = generateLongForm(
                                context = context,
                                text = text,
                                speed = speed,
                                sentencePauseMs = sentencePauseMs.roundToInt(),
                                paragraphPauseMs = paragraphPauseMs.roundToInt(),
                                normalize = normalize,
                                trimSilence = trimSilence,
                                format = format,
                                bitrateKbps = bitrate,
                                onProgress = { value, message -> progress = value; status = message }
                            )
                            outputUri = uri
                            progress = 1f
                            status = "Saved to Music/NekoSpeak Studio"
                            snackbar.showSnackbar("Audio saved successfully")
                        } catch (t: Throwable) {
                            status = "Failed: ${t.message}"
                            snackbar.showSnackbar("Generation failed: ${t.message}")
                        } finally {
                            if (wakeLock.isHeld) wakeLock.release()
                            generating = false
                        }
                    }
                },
                enabled = text.isNotBlank() && !generating,
                modifier = Modifier.fillMaxWidth().height(54.dp)
            ) {
                Icon(Icons.Default.PlayArrow, null)
                Spacer(Modifier.width(8.dp))
                Text(if (generating) "Generating…" else "Generate and save audio")
            }

            outputUri?.let { uri ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { openAudio(context, uri) }) { Text("Play") }
                    OutlinedButton(onClick = { shareAudio(context, uri, format.mimeType) }) {
                        Icon(Icons.Default.Share, null)
                        Spacer(Modifier.width(6.dp))
                        Text("Share")
                    }
                }
            }

            Text(
                "Long text is split at sentence boundaries and streamed directly to a temporary PCM file, so the complete waveform is not held in RAM.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun LabeledSlider(label: String, value: Float, range: ClosedFloatingPointRange<Float>, display: String, onChange: (Float) -> Unit) {
    Column {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(label)
            Text(display, color = MaterialTheme.colorScheme.primary)
        }
        Slider(value = value, onValueChange = onChange, valueRange = range)
    }
}

private suspend fun generateLongForm(
    context: Context,
    text: String,
    speed: Float,
    sentencePauseMs: Int,
    paragraphPauseMs: Int,
    normalize: Boolean,
    trimSilence: Boolean,
    format: StudioAudioFormat,
    bitrateKbps: Int,
    onProgress: (Float, String) -> Unit
): android.net.Uri {
    val engine = EngineFactory.createEngine(context)
    val rawPcm = File(context.cacheDir, "studio_${System.nanoTime()}.pcm")
    try {
        check(withContext(Dispatchers.IO) { engine.initialize() }) {
            "The selected model is not installed or could not be initialized"
        }
        val chunks = splitLongText(text)
        check(chunks.isNotEmpty()) { "No readable text was found" }
        val sampleRate = engine.getSampleRate()
        val voice = PrefsManager(context).currentVoice

        withContext(Dispatchers.IO) {
            BufferedOutputStream(FileOutputStream(rawPcm), 256 * 1024).use { output ->
                chunks.forEachIndexed { index, chunk ->
                    onProgress(index.toFloat() / chunks.size, "Generating segment ${index + 1} of ${chunks.size}")
                    engine.generate(chunk.text, speed, voice) { samples ->
                        val processed = processSamples(samples, normalize, trimSilence)
                        writePcm16(output, processed)
                    }
                    val pause = if (chunk.paragraphEnd) paragraphPauseMs else sentencePauseMs
                    writeSilence(output, sampleRate, pause)
                }
            }
        }

        onProgress(0.96f, "Encoding ${format.name} audio…")
        val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        return AudioFileExporter.export(context, rawPcm, sampleRate, format, bitrateKbps, "NekoSpeak_$stamp")
    } finally {
        runCatching { engine.release() }
        rawPcm.delete()
    }
}

private fun splitLongText(text: String, maxChars: Int = 280): List<StudioChunk> {
    val output = mutableListOf<StudioChunk>()
    val paragraphs = text.replace("\r\n", "\n").split(Regex("\\n\\s*\\n"))
    paragraphs.forEach { paragraphRaw ->
        val paragraph = paragraphRaw.replace(Regex("\\s+"), " ").trim()
        if (paragraph.isEmpty()) return@forEach
        val sentences = paragraph.split(Regex("(?<=[.!?।！？])\\s+"))
        val current = StringBuilder()
        sentences.forEach { sentenceRaw ->
            var sentence = sentenceRaw.trim()
            while (sentence.length > maxChars) {
                val splitAt = sentence.lastIndexOf(' ', maxChars).takeIf { it > maxChars / 2 } ?: maxChars
                val head = sentence.substring(0, splitAt).trim()
                if (current.isNotEmpty()) {
                    output += StudioChunk(current.toString(), false)
                    current.clear()
                }
                if (head.isNotEmpty()) output += StudioChunk(head, false)
                sentence = sentence.substring(splitAt).trim()
            }
            if (sentence.isEmpty()) return@forEach
            if (current.isNotEmpty() && current.length + 1 + sentence.length > maxChars) {
                output += StudioChunk(current.toString(), false)
                current.clear()
            }
            if (current.isNotEmpty()) current.append(' ')
            current.append(sentence)
        }
        if (current.isNotEmpty()) output += StudioChunk(current.toString(), true)
        else if (output.isNotEmpty()) output[output.lastIndex] = output.last().copy(paragraphEnd = true)
    }
    return output
}

private fun processSamples(samples: FloatArray, normalize: Boolean, trim: Boolean): FloatArray {
    if (samples.isEmpty()) return samples
    var start = 0
    var end = samples.size
    if (trim) {
        val threshold = 0.004f
        while (start < end && abs(samples[start]) < threshold) start++
        while (end > start && abs(samples[end - 1]) < threshold) end--
        val keepEdge = 320
        start = (start - keepEdge).coerceAtLeast(0)
        end = (end + keepEdge).coerceAtMost(samples.size)
    }
    val result = samples.copyOfRange(start, end)
    if (normalize && result.isNotEmpty()) {
        val peak = result.maxOf { abs(it) }
        if (peak > 0.001f) {
            val gain = (0.92f / peak).coerceAtMost(4f)
            result.indices.forEach { result[it] = (result[it] * gain).coerceIn(-1f, 1f) }
        }
    }
    return result
}

private fun writePcm16(output: BufferedOutputStream, samples: FloatArray) {
    val buffer = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
    samples.forEach { sample -> buffer.putShort((sample.coerceIn(-1f, 1f) * 32767f).roundToInt().toShort()) }
    output.write(buffer.array())
}

private fun writeSilence(output: BufferedOutputStream, sampleRate: Int, milliseconds: Int) {
    if (milliseconds <= 0) return
    val bytes = (sampleRate.toLong() * milliseconds / 1000L * 2L).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
    val zero = ByteArray(minOf(bytes, 64 * 1024))
    var remaining = bytes
    while (remaining > 0) {
        val count = minOf(remaining, zero.size)
        output.write(zero, 0, count)
        remaining -= count
    }
}

private fun estimateMinutes(text: String, speed: Float): Int {
    val words = text.trim().split(Regex("\\s+")).count { it.isNotBlank() }
    return ((words / (145f * speed.coerceAtLeast(0.5f))).coerceAtLeast(0f)).roundToInt()
}

private fun displayModelName(id: String): String = when (id) {
    "pocket_v1" -> "Pocket-TTS"
    "mms_malayalam" -> "Malayalam Natural"
    "kokoro_v1.0" -> "Kokoro"
    "kitten_nano" -> "Kitten Nano"
    else -> id.removePrefix("piper_")
}

private fun openAudio(context: Context, uri: android.net.Uri) {
    context.startActivity(Intent(Intent.ACTION_VIEW).apply {
        setDataAndType(uri, "audio/*")
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    })
}

private fun shareAudio(context: Context, uri: android.net.Uri, mime: String) {
    context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
        type = mime
        putExtra(Intent.EXTRA_STREAM, uri)
        clipData = ClipData.newUri(context.contentResolver, "NekoSpeak audio", uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }, "Share generated audio"))
}
