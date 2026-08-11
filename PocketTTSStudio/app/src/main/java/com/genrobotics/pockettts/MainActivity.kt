package com.genrobotics.pockettts

import android.media.MediaPlayer
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.OpenableColumns
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import kotlin.math.abs
import kotlin.math.max

class MainActivity : ComponentActivity() {
    private val modelManager by lazy { ModelManager(this) }
    private var engine: PocketEngine? = null
    private var player: MediaPlayer? = null
    private val renderFile by lazy { File(filesDir, "renders/latest.wav").also { it.parentFile?.mkdirs() } }
    private var referenceFile: File? = null

    private var modelReady by mutableStateOf(false)
    private var engineReady by mutableStateOf(false)
    private var modelProgress by mutableStateOf(0)
    private var status by mutableStateOf("Checking PocketTTS model…")
    private var generating by mutableStateOf(false)
    private var streamedSamples by mutableStateOf(0)
    private var waveform by mutableStateOf<FloatArray?>(null)
    private var outputRate by mutableStateOf(24000)
    private var voiceName by mutableStateOf("Default reference voice")

    private val exportLauncher = registerForActivityResult(ActivityResultContracts.CreateDocument("audio/wav")) { uri ->
        if (uri != null) exportWav(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        refreshModelState()
        setContent { PocketStudio() }
    }

    private fun refreshModelState() {
        modelReady = modelManager.isReady()
        if (!modelReady) {
            engineReady = false
            status = "Model not installed • open MODEL"
            modelProgress = 0
            return
        }
        referenceFile = referenceFile ?: modelManager.defaultVoice.takeIf { it.isFile }
        status = "Model verified • ${(modelManager.modelBytes() / 1024 / 1024)} MB"
        modelProgress = 100
        initializeEngine(2)
    }

    private fun initializeEngine(threads: Int) {
        engineReady = false
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                engine?.release()
                val newEngine = PocketEngine(modelManager.modelDir, threads)
                newEngine.initialize()
                engine = newEngine
                withContext(Dispatchers.Main) {
                    engineReady = true
                    status = "READY • CPU INT8 • ${newEngine.sampleRate()} Hz"
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) {
                    engineReady = false
                    status = "Engine error • ${t.message ?: t.javaClass.simpleName}"
                }
            }
        }
    }

    private fun downloadModel() {
        if (modelProgress in 1..99) return
        lifecycleScope.launch {
            try {
                engineReady = false
                modelReady = false
                modelManager.downloadAndInstall { p, message ->
                    runOnUiThread {
                        modelProgress = p
                        status = message
                    }
                }
                modelReady = true
                referenceFile = modelManager.defaultVoice.takeIf { it.isFile }
                voiceName = "Default voice • bria.wav"
                initializeEngine(2)
            } catch (t: Throwable) {
                modelProgress = 0
                status = "Install failed • ${t.message ?: t.javaClass.simpleName}"
                Toast.makeText(this@MainActivity, status, Toast.LENGTH_LONG).show()
            }
        }
    }

    @Composable
    private fun PocketStudio() {
        val bg = Color(0xFF090C12)
        val panel = Color(0xFF141A24)
        val panel2 = Color(0xFF1A2230)
        val cyan = Color(0xFF72E5FF)
        val green = Color(0xFF63F28D)
        val muted = Color(0xFF93A1B6)
        MaterialTheme(
            colors = darkColors(primary = cyan, secondary = green, background = bg, surface = panel)
        ) {
            Surface(modifier = Modifier.fillMaxSize(), color = bg) {
                var tab by remember { mutableStateOf(0) }
                Column(Modifier.fillMaxSize()) {
                    Header(cyan, green, muted)
                    TabRow(selectedTabIndex = tab, backgroundColor = panel, contentColor = cyan) {
                        Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("STUDIO") })
                        Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("MODEL") })
                        Tab(selected = tab == 2, onClick = { tab = 2 }, text = { Text("ABOUT") })
                    }
                    when (tab) {
                        0 -> StudioScreen(panel, panel2, cyan, green, muted)
                        1 -> ModelScreen(panel, cyan, muted)
                        else -> AboutScreen(panel, cyan, muted)
                    }
                }
            }
        }
    }

    @Composable
    private fun Header(cyan: Color, green: Color, muted: Color) {
        Row(
            Modifier.fillMaxWidth().background(Color(0xFF0F141D)).padding(horizontal = 16.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text("POCKET TTS", fontSize = 20.sp, fontWeight = FontWeight.Black, letterSpacing = 1.2.sp)
                Text("ULTRA STUDIO • LOCAL", color = muted, fontSize = 11.sp)
            }
            Surface(
                color = if (engineReady) green.copy(alpha = .14f) else cyan.copy(alpha = .11f),
                shape = RoundedCornerShape(20.dp)
            ) {
                Text(
                    if (engineReady) "● READY" else "● SETUP",
                    color = if (engineReady) green else cyan,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 11.dp, vertical = 7.dp)
                )
            }
        }
    }

    @Composable
    private fun StudioScreen(panel: Color, panel2: Color, cyan: Color, green: Color, muted: Color) {
        var text by remember { mutableStateOf("Pocket TTS Ultra Studio is generating this speech completely on this Android phone.") }
        var speed by remember { mutableStateOf(1.0f) }
        var temperature by remember { mutableStateOf(0.7f) }
        var steps by remember { mutableStateOf(5f) }
        var silence by remember { mutableStateOf(0.2f) }
        var threads by remember { mutableStateOf(2f) }
        var seed by remember { mutableStateOf("-1") }
        var live by remember { mutableStateOf(true) }
        val context = LocalContext.current

        val voicePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
            if (uri != null) importReference(uri)
        }

        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Card(backgroundColor = panel, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text(status, fontWeight = FontWeight.Bold, color = if (engineReady) green else cyan)
                    if (modelProgress in 1..99) LinearProgressIndicator(modelProgress / 100f, Modifier.fillMaxWidth())
                    Text("ARM64 • offline after model install • streaming generation", color = muted, fontSize = 11.sp)
                }
            }

            Card(backgroundColor = panel, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("SCRIPT", color = cyan, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    OutlinedTextField(
                        value = text,
                        onValueChange = { text = it },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 145.dp),
                        label = { Text("Text to synthesize") },
                        maxLines = 15
                    )
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("${text.length} characters", color = muted, fontSize = 11.sp, modifier = Modifier.weight(1f))
                        TextButton(onClick = { text = "" }) { Text("CLEAR") }
                    }
                }
            }

            Card(backgroundColor = panel, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("VOICE LAB", color = cyan, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text(voiceName, fontWeight = FontWeight.SemiBold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { voicePicker.launch(arrayOf("audio/wav", "audio/x-wav", "audio/wave")) },
                            modifier = Modifier.weight(1f)
                        ) { Text("IMPORT WAV") }
                        OutlinedButton(
                            onClick = {
                                referenceFile = modelManager.defaultVoice.takeIf { it.isFile }
                                voiceName = "Default voice • bria.wav"
                            },
                            enabled = modelReady,
                            modifier = Modifier.weight(1f)
                        ) { Text("DEFAULT") }
                    }
                    Text("Use a clean mono speech reference. PocketTTS derives the voice directly from the WAV reference.", color = muted, fontSize = 11.sp)
                }
            }

            Card(backgroundColor = panel, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("GENERATION CONTROL", color = cyan, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    SliderControl("Speed", speed, .5f..2f, "%.2fx") { speed = it }
                    SliderControl("Temperature", temperature, .1f..2f, "%.2f") { temperature = it }
                    SliderControl("Sampling steps", steps, 1f..20f, "%.0f") { steps = it }
                    SliderControl("Silence scale", silence, 0f..1f, "%.2f") { silence = it }
                    SliderControl("CPU threads", threads, 1f..4f, "%.0f") { threads = it }
                    OutlinedTextField(
                        value = seed,
                        onValueChange = { seed = it.filter { c -> c == '-' || c.isDigit() }.take(11) },
                        label = { Text("Seed (-1 = random)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(checked = live, onCheckedChange = { live = it })
                        Spacer(Modifier.width(8.dp))
                        Text("Live streaming playback")
                    }
                }
            }

            Card(backgroundColor = panel2, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("MASTER OUTPUT", color = cyan, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    val samples = waveform
                    if (samples != null && samples.isNotEmpty()) {
                        Waveform(samples, cyan)
                        Text("${samples.size} samples • $outputRate Hz • ${String.format("%.2f", samples.size.toDouble() / outputRate)} s", color = muted, fontSize = 11.sp)
                    } else {
                        Box(Modifier.fillMaxWidth().height(78.dp).background(Color(0xFF0B1018), RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) {
                            Text(if (generating) "Streaming… $streamedSamples samples" else "No rendered audio", color = muted)
                        }
                    }

                    if (!generating) {
                        Button(
                            onClick = {
                                val ref = referenceFile
                                when {
                                    !engineReady -> Toast.makeText(context, "Install/initialize the model first", Toast.LENGTH_SHORT).show()
                                    ref == null || !ref.isFile -> Toast.makeText(context, "Choose a reference WAV", Toast.LENGTH_SHORT).show()
                                    text.isBlank() -> Toast.makeText(context, "Enter text", Toast.LENGTH_SHORT).show()
                                    else -> renderSpeech(text, ref, speed, temperature, steps.toInt(), seed.toIntOrNull() ?: -1, silence, live, threads.toInt())
                                }
                            },
                            enabled = engineReady,
                            modifier = Modifier.fillMaxWidth()
                        ) { Text("GENERATE SPEECH", fontWeight = FontWeight.Bold) }
                    } else {
                        Button(onClick = { engine?.cancelGeneration() }, colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFFFF6B6B)), modifier = Modifier.fillMaxWidth()) {
                            Text("CANCEL RENDER")
                        }
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { playLatest() }, enabled = renderFile.isFile && !generating, modifier = Modifier.weight(1f)) { Text("PLAY") }
                        OutlinedButton(onClick = { exportLauncher.launch("PocketTTS-${System.currentTimeMillis()}.wav") }, enabled = renderFile.isFile && !generating, modifier = Modifier.weight(1f)) { Text("EXPORT WAV") }
                    }
                }
            }
        }
    }

    @Composable
    private fun ModelScreen(panel: Color, cyan: Color, muted: Color) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Card(backgroundColor = panel, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("POCKETTTS INT8", color = cyan, fontWeight = FontWeight.Black)
                    Text("Official sherpa-onnx PocketTTS export")
                    Text("The model is downloaded after APK installation, verified by required filenames, then kept in private app storage.", color = muted, fontSize = 12.sp)
                    LinearProgressIndicator(modelProgress / 100f, Modifier.fillMaxWidth())
                    Text(status, color = muted, fontSize = 12.sp)
                    Button(
                        onClick = { downloadModel() },
                        enabled = modelProgress == 0 || modelProgress == 100,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (modelReady) "REINSTALL MODEL" else "DOWNLOAD MODEL (~203 MB)") }
                    OutlinedButton(
                        onClick = {
                            engine?.release(); engine = null
                            engineReady = false
                            modelManager.deleteModel()
                            modelReady = false
                            modelProgress = 0
                            status = "Model not installed"
                            waveform = null
                        },
                        enabled = modelReady && !generating,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("DELETE MODEL") }
                }
            }
            Card(backgroundColor = panel, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("DEVICE", color = cyan, fontWeight = FontWeight.Black)
                    Text("ABI: ${android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown"}")
                    Text("CPU cores: ${Runtime.getRuntime().availableProcessors()}")
                    Text("Android ${android.os.Build.VERSION.RELEASE} • API ${android.os.Build.VERSION.SDK_INT}")
                    Text("Redmi Note 12 baseline: start at 2 CPU threads; use 3–4 only if your device remains faster under sustained load.", color = muted, fontSize = 12.sp)
                }
            }
        }
    }

    @Composable
    private fun AboutScreen(panel: Color, cyan: Color, muted: Color) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(14.dp)) {
            Card(backgroundColor = panel, shape = RoundedCornerShape(18.dp), elevation = 0.dp) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text("POCKET TTS ULTRA STUDIO", color = cyan, fontWeight = FontWeight.Black)
                    Text("0.1.0 • native Android engineering build")
                    Text("Implemented: on-device PocketTTS, zero-shot voice cloning, runtime model manager, streaming playback, speed/temperature/step/seed/silence controls, CPU thread control, waveform preview, cancel, replay and WAV export.", color = muted, fontSize = 12.sp)
                    Divider()
                    Text("Model license", fontWeight = FontWeight.Bold)
                    Text("The current sherpa-onnx PocketTTS INT8 model card marks the model non-commercial. Check upstream terms before commercial distribution.", color = Color(0xFFFFB86C), fontSize = 12.sp)
                }
            }
        }
    }

    @Composable
    private fun SliderControl(label: String, value: Float, range: ClosedFloatingPointRange<Float>, format: String, onChange: (Float) -> Unit) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, fontSize = 13.sp, modifier = Modifier.weight(1f))
            Text(String.format(format, value), fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
        Slider(value = value, onValueChange = onChange, valueRange = range)
    }

    @Composable
    private fun Waveform(samples: FloatArray, color: Color) {
        Canvas(Modifier.fillMaxWidth().height(88.dp).background(Color(0xFF0B1018), RoundedCornerShape(12.dp)).padding(8.dp)) {
            val mid = size.height / 2f
            drawLine(Color(0xFF30394A), Offset(0f, mid), Offset(size.width, mid), 1f)
            val columns = max(32, size.width.toInt().coerceAtMost(180))
            val stride = max(1, samples.size / columns)
            for (i in 0 until columns) {
                val start = i * stride
                val end = (start + stride).coerceAtMost(samples.size)
                if (start >= end) break
                var peak = 0f
                for (j in start until end) peak = max(peak, abs(samples[j]))
                val x = (i.toFloat() / max(1, columns - 1)) * size.width
                val h = peak.coerceIn(0f, 1f) * mid * .9f
                drawLine(color, Offset(x, mid - h), Offset(x, mid + h), 2f, StrokeCap.Round)
            }
        }
    }

    private fun importReference(uri: Uri) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val dir = File(filesDir, "voices").apply { mkdirs() }
                val file = File(dir, "reference-${System.currentTimeMillis()}.wav")
                contentResolver.openInputStream(uri)?.use { input -> FileOutputStream(file).use { output -> input.copyTo(output) } }
                    ?: error("Cannot open selected file")
                val header = ByteArray(12)
                val read = file.inputStream().use { it.read(header) }
                if (read != 12 || String(header, 0, 4) != "RIFF" || String(header, 8, 4) != "WAVE") {
                    file.delete()
                    error("Reference must be a valid WAV file")
                }
                referenceFile = file
                val displayName = queryDisplayName(uri) ?: file.name
                withContext(Dispatchers.Main) {
                    voiceName = "Cloned voice • $displayName"
                    Toast.makeText(this@MainActivity, "Reference voice loaded", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) { Toast.makeText(this@MainActivity, t.message ?: "Voice import failed", Toast.LENGTH_LONG).show() }
            }
        }
    }

    private fun queryDisplayName(uri: Uri): String? {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) return cursor.getString(0)
        }
        return null
    }

    private fun renderSpeech(text: String, reference: File, speed: Float, temperature: Float, steps: Int, seed: Int, silence: Float, live: Boolean, threads: Int) {
        generating = true
        streamedSamples = 0
        waveform = null
        player?.release(); player = null
        val wakeLock = (getSystemService(POWER_SERVICE) as PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PocketTTS:Render")
        wakeLock.acquire(20 * 60 * 1000L)
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val e = engine ?: error("Engine unavailable")
                e.setThreads(threads)
                val audio = e.generate(text, reference, speed, temperature, steps, seed, silence, live) { count ->
                    runOnUiThread { streamedSamples = count }
                }
                if (audio.samples.isEmpty()) error("Generation cancelled or returned no audio")
                if (!audio.save(renderFile.absolutePath)) error("Failed to save WAV")
                withContext(Dispatchers.Main) {
                    waveform = audio.samples
                    outputRate = audio.sampleRate
                    streamedSamples = audio.samples.size
                    Toast.makeText(this@MainActivity, "Speech generated", Toast.LENGTH_SHORT).show()
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) { Toast.makeText(this@MainActivity, t.message ?: "Generation failed", Toast.LENGTH_LONG).show() }
            } finally {
                if (wakeLock.isHeld) wakeLock.release()
                withContext(Dispatchers.Main) { generating = false }
            }
        }
    }

    private fun playLatest() {
        if (!renderFile.isFile) return
        try {
            player?.release()
            player = MediaPlayer().apply {
                setDataSource(renderFile.absolutePath)
                setOnCompletionListener { completed ->
                    completed.release()
                    if (player === completed) player = null
                }
                prepare()
                start()
            }
        } catch (t: Throwable) {
            Toast.makeText(this, t.message ?: "Playback failed", Toast.LENGTH_LONG).show()
        }
    }

    private fun exportWav(uri: Uri) {
        if (!renderFile.isFile) return
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                contentResolver.openOutputStream(uri, "w")?.use { output -> renderFile.inputStream().use { input -> input.copyTo(output) } }
                    ?: error("Cannot open export location")
                withContext(Dispatchers.Main) { Toast.makeText(this@MainActivity, "WAV exported", Toast.LENGTH_SHORT).show() }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) { Toast.makeText(this@MainActivity, t.message ?: "Export failed", Toast.LENGTH_LONG).show() }
            }
        }
    }

    override fun onDestroy() {
        player?.release()
        engine?.release()
        super.onDestroy()
    }
}
