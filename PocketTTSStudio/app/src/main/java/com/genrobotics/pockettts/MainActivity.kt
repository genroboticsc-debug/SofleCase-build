package com.genrobotics.pockettts

import android.content.Context
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
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
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
    private val prefs by lazy { getSharedPreferences("studio", Context.MODE_PRIVATE) }

    private var pocketEngine: PocketEngine? = null
    private var piperEngine: PiperEngine? = null
    private var activeThreads = -1
    private var player: MediaPlayer? = null

    private val renderFile by lazy { File(filesDir, "renders/latest_master.wav").also { it.parentFile?.mkdirs() } }
    private val rawFile by lazy { File(filesDir, "renders/latest_raw.wav").also { it.parentFile?.mkdirs() } }
    private val takesDir by lazy { File(filesDir, "renders/takes").also { it.mkdirs() } }
    private val voicesDir by lazy { File(filesDir, "voices").also { it.mkdirs() } }

    private var referenceFile: File? = null
    private var lastRawAudio: SynthAudio? = null

    private var selectedPackId by mutableStateOf("pocket_en")
    private var scriptText by mutableStateOf(ModelCatalog.byId("pocket_en").sampleText)
    private var engineReady by mutableStateOf(false)
    private var status by mutableStateOf("Initializing studio…")
    private var generating by mutableStateOf(false)
    private var streamedSamples by mutableStateOf(0)
    private var waveform by mutableStateOf<FloatArray?>(null)
    private var outputRate by mutableStateOf(24000)
    private var voiceName by mutableStateOf("Default • bria.wav")
    private var installingPackId by mutableStateOf<String?>(null)
    private var installProgress by mutableStateOf(0)
    private var installMessage by mutableStateOf("")
    private var takes by mutableStateOf<List<RenderTake>>(emptyList())
    private var voiceProfiles by mutableStateOf<List<File>>(emptyList())
    private var lastRtf by mutableStateOf(0.0)
    private var lastPeakDb by mutableStateOf(-120.0)
    private var lastRmsDb by mutableStateOf(-120.0)

    private var speed by mutableStateOf(1.0f)
    private var temperature by mutableStateOf(0.7f)
    private var steps by mutableStateOf(5f)
    private var silence by mutableStateOf(0.2f)
    private var seedText by mutableStateOf("-1")
    private var speakerId by mutableStateOf(0f)
    private var threads by mutableStateOf(2f)
    private var livePlayback by mutableStateOf(true)

    private var masterDc by mutableStateOf(true)
    private var masterTrim by mutableStateOf(true)
    private var masterNormalize by mutableStateOf(true)
    private var masterLimiter by mutableStateOf(true)
    private var masterPeakTarget by mutableStateOf(-1.0f)
    private var masterGain by mutableStateOf(0.0f)
    private var masterFadeMs by mutableStateOf(8f)
    private var uiMalayalam by mutableStateOf(false)

    private val exportLauncher = registerForActivityResult(ActivityResultContracts.CreateDocument("audio/wav")) { uri ->
        if (uri != null) exportWav(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        selectedPackId = prefs.getString("pack", "pocket_en") ?: "pocket_en"
        threads = prefs.getFloat("threads", 2f).coerceIn(1f, 4f)
        livePlayback = prefs.getBoolean("live", true)
        uiMalayalam = prefs.getBoolean("ui_ml", false)
        refreshProfiles()
        selectPack(ModelCatalog.byId(selectedPackId), keepScript = true)
        setContent { UltraStudioApp() }
    }

    private fun selectedPack(): ModelPack = ModelCatalog.byId(selectedPackId)

    private fun selectPack(pack: ModelPack, keepScript: Boolean = false) {
        selectedPackId = pack.id
        prefs.edit().putString("pack", pack.id).apply()
        speakerId = 0f
        if (!keepScript) scriptText = pack.sampleText
        releaseEngines()
        engineReady = false

        if (!modelManager.isReady(pack)) {
            status = "${pack.displayName} • model not installed"
            return
        }

        if (pack.engine == EngineKind.POCKET) {
            val default = modelManager.defaultVoice(pack)
            if (referenceFile == null || referenceFile?.isFile != true) {
                referenceFile = default.takeIf { it.isFile }
                voiceName = if (default.isFile) "Default • bria.wav" else "Reference WAV required"
            }
        }
        initializeEngine(pack, threads.toInt())
    }

    private fun initializeEngine(pack: ModelPack, threadCount: Int) {
        releaseEngines()
        engineReady = false
        status = "Loading ${pack.voiceName}…"
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                when (pack.engine) {
                    EngineKind.POCKET -> {
                        val e = PocketEngine(modelManager.dir(pack), threadCount)
                        e.initialize()
                        pocketEngine = e
                        outputRate = e.sampleRate()
                    }
                    EngineKind.PIPER -> {
                        val e = PiperEngine(modelManager.dir(pack), pack, threadCount)
                        e.initialize()
                        piperEngine = e
                        outputRate = e.sampleRate()
                    }
                }
                activeThreads = threadCount
                withContext(Dispatchers.Main) {
                    engineReady = true
                    status = "READY • ${engineLabel(pack)} • $outputRate Hz • ${threadCount}T CPU"
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) {
                    engineReady = false
                    status = "Engine error • ${t.message ?: t.javaClass.simpleName}"
                }
            }
        }
    }

    private fun engineLabel(pack: ModelPack): String =
        if (pack.engine == EngineKind.POCKET) "KYUTAI POCKETTTS" else "PIPER / SHERPA"

    private fun installPack(pack: ModelPack) {
        if (installingPackId != null) return
        installingPackId = pack.id
        installProgress = 0
        installMessage = "Preparing ${pack.displayName}…"
        lifecycleScope.launch {
            try {
                if (pack.id == selectedPackId) {
                    releaseEngines()
                    engineReady = false
                }
                modelManager.install(pack) { progress, message ->
                    runOnUiThread {
                        installProgress = progress
                        installMessage = message
                    }
                }
                installProgress = 100
                installMessage = "Verified • ${pack.displayName}"
                if (pack.id == selectedPackId) selectPack(pack, keepScript = true)
            } catch (t: Throwable) {
                installProgress = 0
                installMessage = "Install failed • ${t.message ?: t.javaClass.simpleName}"
                Toast.makeText(this@MainActivity, installMessage, Toast.LENGTH_LONG).show()
            } finally {
                installingPackId = null
            }
        }
    }

    private fun deletePack(pack: ModelPack) {
        if (generating || installingPackId != null) return
        if (pack.id == selectedPackId) {
            releaseEngines()
            engineReady = false
        }
        modelManager.delete(pack)
        if (pack.id == selectedPackId) status = "${pack.displayName} • model removed"
    }

    private fun currentMastering() = StudioAudio.Mastering(
        dcRemove = masterDc,
        trimSilence = masterTrim,
        normalize = masterNormalize,
        limiter = masterLimiter,
        targetPeakDb = masterPeakTarget,
        outputGainDb = masterGain,
        fadeMs = masterFadeMs.toInt()
    )

    private fun renderSpeech() {
        val pack = selectedPack()
        val ref = referenceFile
        when {
            generating -> return
            scriptText.isBlank() -> toast("Enter text first")
            !modelManager.isReady(pack) -> toast("Install ${pack.displayName} in MODELS")
            pack.engine == EngineKind.POCKET && (ref == null || !ref.isFile) -> toast("Choose a reference WAV in VOICE LAB")
        }
        if (scriptText.isBlank() || !modelManager.isReady(pack) || (pack.engine == EngineKind.POCKET && (ref == null || !ref.isFile))) return

        if (!engineReady || activeThreads != threads.toInt()) {
            initializeEngine(pack, threads.toInt())
            toast("Engine is loading with the selected CPU thread count")
            return
        }

        val capturedText = scriptText
        val capturedSpeed = speed
        val capturedTemp = temperature
        val capturedSteps = steps.toInt()
        val capturedSeed = seedText.toIntOrNull() ?: -1
        val capturedSilence = silence
        val capturedSpeaker = speakerId.toInt()
        val capturedLive = livePlayback
        val mastering = currentMastering()

        generating = true
        streamedSamples = 0
        waveform = null
        status = "Rendering • ${pack.displayName}"
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        val wake = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PocketTTS:Render")
        wake.acquire(10 * 60 * 1000L)
        val startedNs = System.nanoTime()

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val raw = when (pack.engine) {
                    EngineKind.POCKET -> pocketEngine!!.generate(
                        text = capturedText,
                        referenceWav = ref!!,
                        speed = capturedSpeed,
                        temperature = capturedTemp,
                        steps = capturedSteps,
                        seed = capturedSeed,
                        silence = capturedSilence,
                        livePlayback = capturedLive
                    ) { count -> runOnUiThread { streamedSamples = count } }
                    EngineKind.PIPER -> piperEngine!!.generate(
                        text = capturedText,
                        speed = capturedSpeed,
                        silence = capturedSilence,
                        speakerId = capturedSpeaker,
                        livePlayback = capturedLive
                    ) { count -> runOnUiThread { streamedSamples = count } }
                }

                if (raw.samples.isEmpty()) {
                    withContext(Dispatchers.Main) {
                        status = "Render cancelled"
                        generating = false
                    }
                    return@launch
                }

                lastRawAudio = raw
                raw.save(rawFile.absolutePath)
                val mastered = StudioAudio.process(raw, mastering)
                check(mastered.samples.isNotEmpty()) { "Mastering produced empty audio" }
                check(mastered.save(renderFile.absolutePath)) { "Could not write master WAV" }

                val now = System.currentTimeMillis()
                val takeFile = File(takesDir, "take_${now}_${pack.languageCode}_${pack.voiceName.replace(' ', '_')}.wav")
                mastered.save(takeFile.absolutePath)
                val elapsed = (System.nanoTime() - startedNs) / 1_000_000_000.0
                val rtf = if (mastered.durationSeconds > 0) elapsed / mastered.durationSeconds else 0.0
                val peak = StudioAudio.peakDb(mastered.samples)
                val rms = StudioAudio.rmsDb(mastered.samples)
                val title = capturedText.trim().replace("\n", " ").take(54)
                val take = RenderTake(takeFile, pack.id, title, now, mastered.durationSeconds, mastered.sampleRate, rtf, peak)

                withContext(Dispatchers.Main) {
                    outputRate = mastered.sampleRate
                    waveform = mastered.samples
                    lastRtf = rtf
                    lastPeakDb = peak
                    lastRmsDb = rms
                    takes = (listOf(take) + takes).take(8)
                    status = "RENDERED • ${String.format("%.2f", mastered.durationSeconds)} s • RTF ${String.format("%.2f", rtf)}"
                    generating = false
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) {
                    status = "Render failed • ${t.message ?: t.javaClass.simpleName}"
                    generating = false
                    toast(status)
                }
            } finally {
                if (wake.isHeld) wake.release()
            }
        }
    }

    private fun cancelRender() {
        pocketEngine?.cancelGeneration()
        piperEngine?.cancelGeneration()
        status = "Cancelling render…"
    }

    private fun remasterLatest() {
        val raw = lastRawAudio ?: run {
            toast("Generate audio first")
            return
        }
        lifecycleScope.launch(Dispatchers.Default) {
            val mastered = StudioAudio.process(raw, currentMastering())
            mastered.save(renderFile.absolutePath)
            withContext(Dispatchers.Main) {
                waveform = mastered.samples
                outputRate = mastered.sampleRate
                lastPeakDb = StudioAudio.peakDb(mastered.samples)
                lastRmsDb = StudioAudio.rmsDb(mastered.samples)
                status = "Master chain reapplied • peak ${String.format("%.1f", lastPeakDb)} dBFS"
            }
        }
    }

    @Composable
    private fun UltraStudioApp() {
        val c = StudioColors
        MaterialTheme(
            colors = darkColors(
                primary = c.accent,
                secondary = c.green,
                background = c.bg,
                surface = c.surface,
                onSurface = c.text,
                onBackground = c.text
            )
        ) {
            Surface(Modifier.fillMaxSize(), color = c.bg) {
                Box(
                    Modifier.fillMaxSize().background(
                        Brush.verticalGradient(listOf(Color(0xFF0A0E16), Color(0xFF05070B)))
                    )
                ) {
                    var tab by remember { mutableStateOf(0) }
                    Column(Modifier.fillMaxSize()) {
                        StudioHeader()
                        ScrollableTabRow(
                            selectedTabIndex = tab,
                            backgroundColor = c.surface,
                            contentColor = c.accent,
                            edgePadding = 8.dp
                        ) {
                            listOf("STUDIO", "VOICE LAB", "MODELS", "MASTER", "SETTINGS").forEachIndexed { i, label ->
                                Tab(selected = tab == i, onClick = { tab = i }, text = {
                                    Text(label, fontSize = 11.sp, fontWeight = if (tab == i) FontWeight.Bold else FontWeight.Normal)
                                })
                            }
                        }
                        when (tab) {
                            0 -> StudioScreen { tab = 2 }
                            1 -> VoiceLabScreen()
                            2 -> ModelsScreen()
                            3 -> MasterScreen()
                            else -> SettingsScreen()
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun StudioHeader() {
        val c = StudioColors
        val pack = selectedPack()
        Row(
            Modifier.fillMaxWidth().background(c.surface.copy(alpha = 0.97f)).padding(horizontal = 16.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text("POCKET TTS ULTRA", fontSize = 19.sp, fontWeight = FontWeight.Black, letterSpacing = 1.0.sp)
                Text("PRODUCTION STUDIO • LOCAL AI", color = c.muted, fontSize = 10.sp, letterSpacing = 0.8.sp)
            }
            Column(horizontalAlignment = Alignment.End) {
                StatusBadge(if (engineReady) "● READY" else if (installingPackId != null) "● INSTALLING" else "● OFFLINE", engineReady)
                Spacer(Modifier.height(3.dp))
                Text(pack.nativeLanguageName, color = c.muted, fontSize = 10.sp)
            }
        }
    }

    @Composable
    private fun StudioScreen(openModels: () -> Unit) {
        val c = StudioColors
        val pack = selectedPack()
        val context = LocalContext.current
        val refPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
            if (uri != null) importReference(uri)
        }

        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionCard {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(pack.displayName, fontWeight = FontWeight.Black, fontSize = 16.sp)
                        Text(engineLabel(pack), color = if (pack.engine == EngineKind.POCKET) c.purple else c.green, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                    CapabilityBadge(if (pack.cloneVoice) "VOICE CLONE" else "LOCAL VOICE", pack.cloneVoice)
                }
                Spacer(Modifier.height(7.dp))
                Text(status, color = if (engineReady) c.green else c.accent, fontSize = 12.sp)
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    MetricPill("${pack.sampleRateHint / 1000.0} kHz")
                    MetricPill("ARM64")
                    MetricPill("${threads.toInt()}T")
                    MetricPill(if (livePlayback) "LIVE" else "OFFLINE")
                }
            }

            Text("LANGUAGE", color = c.muted, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                ModelCatalog.languages.forEach { code ->
                    val p = ModelCatalog.languagePacks(code).first()
                    ChoiceChip(
                        label = p.nativeLanguageName,
                        selected = p.languageCode == pack.languageCode,
                        onClick = { selectPack(p) }
                    )
                }
            }

            val sameLanguage = ModelCatalog.languagePacks(pack.languageCode)
            if (sameLanguage.size > 1) {
                Text("VOICE", color = c.muted, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    sameLanguage.forEach { p ->
                        ChoiceChip(label = p.voiceName, selected = p.id == pack.id, onClick = { selectPack(p) })
                    }
                }
            }

            SectionCard {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("SCRIPT / SSML-FREE COMPOSER", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    Text("${scriptText.length} chars", color = c.muted, fontSize = 10.sp)
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = scriptText,
                    onValueChange = { scriptText = it },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 155.dp),
                    label = { Text(if (uiMalayalam) "സംസാരിക്കേണ്ട ടെക്സ്റ്റ്" else "Text to synthesize") },
                    maxLines = 18
                )
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { scriptText = pack.sampleText }) { Text("SAMPLE") }
                    TextButton(onClick = { scriptText = "" }) { Text("CLEAR") }
                    Spacer(Modifier.weight(1f))
                    Text(pack.languageName, color = c.muted, fontSize = 10.sp)
                }
            }

            if (pack.engine == EngineKind.POCKET) {
                SectionCard {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("VOICE CLONE REFERENCE", color = c.purple, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            Text(voiceName, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        CapabilityBadge("ZERO-SHOT", true)
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { refPicker.launch(arrayOf("audio/wav", "audio/x-wav", "audio/wave")) }, modifier = Modifier.weight(1f)) {
                            Text("IMPORT WAV")
                        }
                        OutlinedButton(onClick = { useDefaultReference() }, enabled = modelManager.isReady(pack), modifier = Modifier.weight(1f)) {
                            Text("DEFAULT")
                        }
                    }
                    Text("Clean speech works best. Reference transcript is not required by PocketTTS.", color = c.muted, fontSize = 10.sp)
                }
            }

            SectionCard {
                Text("SYNTHESIS", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                SliderControl("Speed", speed, 0.5f..2.0f, "%.2fx") { speed = it }
                SliderControl("Pause / silence", silence, 0f..1f, "%.2f") { silence = it }
                if (pack.engine == EngineKind.POCKET) {
                    SliderControl("Temperature", temperature, 0.1f..2.0f, "%.2f") { temperature = it }
                    SliderControl("Sampling steps", steps, 1f..30f, "%.0f") { steps = it }
                    OutlinedTextField(
                        value = seedText,
                        onValueChange = { seedText = it.filter { ch -> ch == '-' || ch.isDigit() }.take(11) },
                        label = { Text("Seed (-1 = random)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                if (pack.speakers > 1) {
                    SliderControl("Speaker ID", speakerId, 0f..(pack.speakers - 1).toFloat(), "%.0f") { speakerId = it }
                }
            }

            SectionCard(highlight = true) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("MASTER OUTPUT", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    if (waveform != null) Text("${outputRate} Hz", color = c.muted, fontSize = 10.sp)
                }
                Spacer(Modifier.height(8.dp))
                val samples = waveform
                if (samples != null && samples.isNotEmpty()) {
                    Waveform(samples)
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        MetricPill("PK ${String.format("%.1f", lastPeakDb)} dB")
                        MetricPill("RMS ${String.format("%.1f", lastRmsDb)}")
                        MetricPill("RTF ${String.format("%.2f", lastRtf)}")
                    }
                } else {
                    Box(
                        Modifier.fillMaxWidth().height(92.dp).background(c.deep, RoundedCornerShape(14.dp)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(if (generating) "STREAMING • $streamedSamples samples" else "NO RENDER YET", color = c.muted, fontSize = 11.sp)
                    }
                }
                Spacer(Modifier.height(10.dp))

                if (!modelManager.isReady(pack)) {
                    Button(onClick = openModels, modifier = Modifier.fillMaxWidth()) { Text("INSTALL ${pack.voiceName.uppercase()} MODEL") }
                } else if (!generating) {
                    Button(onClick = { renderSpeech() }, enabled = engineReady, modifier = Modifier.fillMaxWidth().height(50.dp)) {
                        Text(if (engineReady) "GENERATE / RENDER" else "LOADING ENGINE…", fontWeight = FontWeight.Black)
                    }
                } else {
                    Button(
                        onClick = { cancelRender() },
                        colors = ButtonDefaults.buttonColors(backgroundColor = c.red),
                        modifier = Modifier.fillMaxWidth().height(50.dp)
                    ) { Text("CANCEL RENDER", fontWeight = FontWeight.Bold) }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { playFile(renderFile) }, enabled = renderFile.isFile && !generating, modifier = Modifier.weight(1f)) { Text("PLAY") }
                    OutlinedButton(
                        onClick = { exportLauncher.launch("PocketTTS-Ultra-${System.currentTimeMillis()}.wav") },
                        enabled = renderFile.isFile && !generating,
                        modifier = Modifier.weight(1f)
                    ) { Text("EXPORT WAV") }
                }
            }

            if (takes.isNotEmpty()) {
                Text("TAKE HISTORY / A-B", color = c.muted, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                takes.forEachIndexed { index, take -> TakeCard(index + 1, take) }
            }

            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun VoiceLabScreen() {
        val c = StudioColors
        val pack = selectedPack()
        val refPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
            if (uri != null) importReference(uri)
        }

        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionCard(highlight = true) {
                Text("VOICE LAB", fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("Reference voices, local neural voice packs and cloning workflow", color = c.muted, fontSize = 11.sp)
            }

            SectionCard {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("KYUTAI ZERO-SHOT CLONE", color = c.purple, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        Text(voiceName, fontWeight = FontWeight.Bold)
                    }
                    CapabilityBadge("POCKETTTS", true)
                }
                Spacer(Modifier.height(9.dp))
                Text("Import a clean WAV reference. The app stores it in private local storage and PocketTTS derives voice identity locally.", color = c.muted, fontSize = 11.sp)
                Spacer(Modifier.height(9.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { refPicker.launch(arrayOf("audio/wav", "audio/x-wav", "audio/wave")) }, modifier = Modifier.weight(1f)) { Text("IMPORT VOICE") }
                    OutlinedButton(onClick = { useDefaultReference() }, enabled = modelManager.isReady(ModelCatalog.byId("pocket_en")), modifier = Modifier.weight(1f)) { Text("BRIA") }
                }
            }

            if (voiceProfiles.isNotEmpty()) {
                Text("LOCAL CLONE PROFILES", color = c.muted, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                voiceProfiles.forEach { file ->
                    Surface(
                        color = if (referenceFile?.absolutePath == file.absolutePath) c.accent.copy(alpha = .12f) else c.surface2,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth().clickable {
                            referenceFile = file
                            voiceName = file.nameWithoutExtension
                            if (selectedPack().engine == EngineKind.POCKET) status = "Voice profile selected • ${file.nameWithoutExtension}"
                        }
                    ) {
                        Row(Modifier.padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(file.nameWithoutExtension, fontWeight = FontWeight.Bold)
                                Text(modelManager.formatBytes(file.length()), color = c.muted, fontSize = 10.sp)
                            }
                            Text("USE", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }

            Text("NEURAL VOICE LIBRARY", color = c.muted, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            ModelCatalog.packs.filter { it.engine == EngineKind.PIPER }.forEach { p ->
                Surface(
                    color = if (pack.id == p.id) c.green.copy(alpha = .10f) else c.surface2,
                    shape = RoundedCornerShape(15.dp),
                    modifier = Modifier.fillMaxWidth().clickable { selectPack(p) }
                ) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${p.nativeLanguageName} • ${p.voiceName}", fontWeight = FontWeight.Black)
                            Text("${p.quality} • ${p.sampleRateHint} Hz", color = c.muted, fontSize = 10.sp)
                        }
                        CapabilityBadge(if (modelManager.isReady(p)) "INSTALLED" else "PACK", false)
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun ModelsScreen() {
        val c = StudioColors
        val installed = modelManager.installedPacks()
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionCard(highlight = true) {
                Text("MODEL VAULT", fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("${installed.size}/${ModelCatalog.packs.size} packs installed • ${modelManager.formatBytes(modelManager.totalInstalledBytes())}", color = c.muted, fontSize = 11.sp)
                if (installingPackId != null) {
                    Spacer(Modifier.height(8.dp))
                    LinearProgressIndicator(installProgress / 100f, Modifier.fillMaxWidth())
                    Text(installMessage, color = c.accent, fontSize = 10.sp)
                }
            }

            ModelCatalog.packs.forEach { pack ->
                val ready = modelManager.isReady(pack)
                SectionCard {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(pack.displayName, fontWeight = FontWeight.Black, fontSize = 15.sp)
                            Text("${engineLabel(pack)} • ${pack.quality}", color = if (pack.engine == EngineKind.POCKET) c.purple else c.green, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        }
                        CapabilityBadge(if (ready) "VERIFIED" else "NOT INSTALLED", ready)
                    }
                    Spacer(Modifier.height(7.dp))
                    Text(pack.description, color = c.muted, fontSize = 11.sp)
                    Spacer(Modifier.height(7.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        MetricPill(pack.nativeLanguageName)
                        MetricPill("${pack.sampleRateHint} Hz")
                        if (pack.cloneVoice) MetricPill("CLONE")
                        if (pack.speakers > 1) MetricPill("${pack.speakers} SPK")
                    }
                    Spacer(Modifier.height(9.dp))
                    if (installingPackId == pack.id) {
                        LinearProgressIndicator(installProgress / 100f, Modifier.fillMaxWidth())
                        Spacer(Modifier.height(4.dp))
                        Text(installMessage, color = c.accent, fontSize = 10.sp)
                    } else if (!ready) {
                        Button(onClick = { installPack(pack) }, enabled = installingPackId == null, modifier = Modifier.fillMaxWidth()) {
                            Text("DOWNLOAD + VERIFY")
                        }
                    } else {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { selectPack(pack) }, modifier = Modifier.weight(1f)) { Text(if (pack.id == selectedPackId) "ACTIVE" else "USE") }
                            OutlinedButton(onClick = { deletePack(pack) }, enabled = installingPackId == null && !generating, modifier = Modifier.weight(1f)) { Text("REMOVE") }
                        }
                        Text("Installed size • ${modelManager.formatBytes(modelManager.modelBytes(pack))}", color = c.muted, fontSize = 10.sp)
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun MasterScreen() {
        val c = StudioColors
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionCard(highlight = true) {
                Text("MASTER / DSP", fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("Non-destructive settings are applied after synthesis and before WAV export.", color = c.muted, fontSize = 11.sp)
            }

            SectionCard {
                Text("CLEANUP", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                ToggleRow("DC offset removal", "Subtract measured waveform mean before mastering", masterDc) { masterDc = it }
                ToggleRow("Silence trim", "Trim below ~-50 dBFS with 35 ms guard", masterTrim) { masterTrim = it }
                ToggleRow("Peak normalize", "Normalize to the configured mastering ceiling", masterNormalize) { masterNormalize = it }
            }

            SectionCard {
                Text("DYNAMICS", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                ToggleRow("Smooth limiter", "Soft saturation above 0.92 FS, then export protection", masterLimiter) { masterLimiter = it }
                SliderControl("Target peak", masterPeakTarget, -6f..-0.2f, "%.1f dBFS") { masterPeakTarget = it }
                SliderControl("Output gain", masterGain, -12f..12f, "%+.1f dB") { masterGain = it }
                SliderControl("Edge fade", masterFadeMs, 0f..50f, "%.0f ms") { masterFadeMs = it }
            }

            SectionCard {
                Text("ANALYSIS", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    MetricPill("Peak ${String.format("%.1f", lastPeakDb)} dBFS")
                    MetricPill("RMS ${String.format("%.1f", lastRmsDb)} dBFS")
                }
                Spacer(Modifier.height(8.dp))
                Button(onClick = { remasterLatest() }, enabled = lastRawAudio != null && !generating, modifier = Modifier.fillMaxWidth()) {
                    Text("REMASTER LAST RAW TAKE")
                }
                Text("The original raw synthesis is kept separately so mastering changes do not require rerunning the neural model.", color = c.muted, fontSize = 10.sp)
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun SettingsScreen() {
        val c = StudioColors
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionCard(highlight = true) {
                Text("ENGINE / DEVICE", fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("Tune sustained inference for your phone instead of chasing a synthetic benchmark.", color = c.muted, fontSize = 11.sp)
            }

            SectionCard {
                Text("PERFORMANCE", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                SliderControl("CPU threads", threads, 1f..4f, "%.0f") {
                    threads = it
                    prefs.edit().putFloat("threads", it).apply()
                    engineReady = activeThreads == it.toInt() && engineReady
                }
                ToggleRow("Live streaming playback", "Play chunks while the neural engine is generating", livePlayback) {
                    livePlayback = it
                    prefs.edit().putBoolean("live", it).apply()
                }
                Text("A thread-count change is applied on the next engine initialization. 2 threads is a conservative mobile starting point.", color = c.muted, fontSize = 10.sp)
            }

            SectionCard {
                Text("INTERFACE", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                ToggleRow("Malayalam UI assist", "Adds Malayalam wording to key studio interactions", uiMalayalam) {
                    uiMalayalam = it
                    prefs.edit().putBoolean("ui_ml", it).apply()
                }
                if (uiMalayalam) Text("മലയാളം മോഡ് സജീവമാണ് • ശബ്ദ മോഡലുകൾ പൂർണ്ണമായും ലോക്കൽ", color = c.green, fontSize = 12.sp)
            }

            SectionCard {
                Text("DEVICE TELEMETRY", color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                KeyValue("ABI", android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
                KeyValue("CPU cores", Runtime.getRuntime().availableProcessors().toString())
                KeyValue("Android", "${android.os.Build.VERSION.RELEASE} • API ${android.os.Build.VERSION.SDK_INT}")
                KeyValue("Installed models", modelManager.formatBytes(modelManager.totalInstalledBytes()))
                KeyValue("App package", packageName)
            }

            SectionCard {
                Text("LOCAL-FIRST", color = c.green, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Text("Synthesis, voice references, takes and mastering stay on-device. Internet is only used when you explicitly download a model pack.", color = c.muted, fontSize = 11.sp)
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun SectionCard(highlight: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
        val c = StudioColors
        Card(
            backgroundColor = if (highlight) c.surface2 else c.surface,
            shape = RoundedCornerShape(20.dp),
            elevation = 0.dp,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(3.dp), content = content)
        }
    }

    @Composable
    private fun ChoiceChip(label: String, selected: Boolean, onClick: () -> Unit) {
        val c = StudioColors
        Surface(
            color = if (selected) c.accent.copy(alpha = .18f) else c.surface2,
            shape = RoundedCornerShape(18.dp),
            modifier = Modifier.clickable(onClick = onClick)
        ) {
            Text(
                label,
                color = if (selected) c.accent else c.text,
                fontSize = 11.sp,
                fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp)
            )
        }
    }

    @Composable
    private fun StatusBadge(text: String, ready: Boolean) {
        val c = StudioColors
        Surface(color = (if (ready) c.green else c.accent).copy(alpha = .12f), shape = RoundedCornerShape(18.dp)) {
            Text(text, color = if (ready) c.green else c.accent, fontSize = 10.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp))
        }
    }

    @Composable
    private fun CapabilityBadge(text: String, special: Boolean) {
        val c = StudioColors
        val color = if (special) c.purple else c.green
        Surface(color = color.copy(alpha = .11f), shape = RoundedCornerShape(13.dp)) {
            Text(text, color = color, fontSize = 9.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp))
        }
    }

    @Composable
    private fun MetricPill(text: String) {
        val c = StudioColors
        Surface(color = c.deep, shape = RoundedCornerShape(12.dp)) {
            Text(text, color = c.muted, fontSize = 9.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp))
        }
    }

    @Composable
    private fun SliderControl(label: String, value: Float, range: ClosedFloatingPointRange<Float>, format: String, onChange: (Float) -> Unit) {
        val c = StudioColors
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(label, fontSize = 12.sp, modifier = Modifier.weight(1f))
            Text(String.format(format, value), color = c.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        }
        Slider(value = value.coerceIn(range.start, range.endInclusive), onValueChange = onChange, valueRange = range)
    }

    @Composable
    private fun ToggleRow(title: String, subtitle: String, checked: Boolean, onChange: (Boolean) -> Unit) {
        val c = StudioColors
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Text(subtitle, color = c.muted, fontSize = 9.sp)
            }
            Switch(checked = checked, onCheckedChange = onChange)
        }
    }

    @Composable
    private fun KeyValue(key: String, value: String) {
        val c = StudioColors
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
            Text(key, color = c.muted, fontSize = 11.sp, modifier = Modifier.weight(1f))
            Text(value, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
    }

    @Composable
    private fun TakeCard(number: Int, take: RenderTake) {
        val c = StudioColors
        val pack = ModelCatalog.byId(take.packId)
        Surface(color = c.surface2, shape = RoundedCornerShape(15.dp), modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Surface(color = c.accent.copy(alpha = .12f), shape = RoundedCornerShape(10.dp)) {
                    Text("T$number", color = c.accent, fontWeight = FontWeight.Black, fontSize = 10.sp, modifier = Modifier.padding(8.dp))
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(take.title.ifBlank { "Untitled take" }, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    Text("${pack.voiceName} • ${String.format("%.2f", take.durationSeconds)} s • RTF ${String.format("%.2f", take.rtf)} • ${String.format("%.1f", take.peakDb)} dBFS", color = c.muted, fontSize = 9.sp)
                }
                TextButton(onClick = { playFile(take.file) }) { Text("A/B") }
            }
        }
    }

    @Composable
    private fun Waveform(samples: FloatArray) {
        val c = StudioColors
        Canvas(Modifier.fillMaxWidth().height(104.dp).background(c.deep, RoundedCornerShape(14.dp)).padding(8.dp)) {
            if (samples.isEmpty()) return@Canvas
            val mid = size.height / 2f
            val columns = max(1, size.width.toInt())
            val stride = max(1, samples.size / columns)
            var x = 0
            var index = 0
            while (x < columns && index < samples.size) {
                val end = (index + stride).coerceAtMost(samples.size)
                var peak = 0f
                var i = index
                while (i < end) {
                    peak = max(peak, abs(samples[i]))
                    i++
                }
                val amp = peak.coerceIn(0f, 1f) * (size.height * 0.46f)
                drawLine(c.accent, Offset(x.toFloat(), mid - amp), Offset(x.toFloat(), mid + amp), strokeWidth = 1.6f, cap = StrokeCap.Round)
                index = end
                x++
            }
            drawLine(c.muted.copy(alpha = .18f), Offset(0f, mid), Offset(size.width, mid), strokeWidth = 1f)
        }
    }

    private fun importReference(uri: Uri) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                voicesDir.mkdirs()
                val sourceName = queryName(uri).ifBlank { "voice_${System.currentTimeMillis()}.wav" }
                val cleanName = sourceName.substringBeforeLast('.').replace(Regex("[^A-Za-z0-9_-]+"), "_").take(48).ifBlank { "voice" }
                val target = File(voicesDir, "${cleanName}_${System.currentTimeMillis()}.wav")
                contentResolver.openInputStream(uri)?.use { input -> FileOutputStream(target).use { output -> input.copyTo(output) } }
                    ?: throw IllegalStateException("Cannot read selected file")
                require(target.length() > 44) { "WAV file is empty" }
                withContext(Dispatchers.Main) {
                    referenceFile = target
                    voiceName = cleanName
                    refreshProfiles()
                    status = "Voice profile imported • $cleanName"
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) { toast("Voice import failed • ${t.message}") }
            }
        }
    }

    private fun useDefaultReference() {
        val p = ModelCatalog.byId("pocket_en")
        val f = modelManager.defaultVoice(p)
        if (f.isFile) {
            referenceFile = f
            voiceName = "Default • bria.wav"
            status = "PocketTTS default reference selected"
        } else toast("Install the PocketTTS model first")
    }

    private fun refreshProfiles() {
        voicesDir.mkdirs()
        voiceProfiles = voicesDir.listFiles()?.filter { it.isFile && it.extension.equals("wav", true) }?.sortedByDescending { it.lastModified() } ?: emptyList()
    }

    private fun queryName(uri: Uri): String {
        var result = ""
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) result = cursor.getString(0) ?: ""
        }
        return result
    }

    private fun playFile(file: File) {
        if (!file.isFile) return
        try {
            player?.release()
            player = MediaPlayer().apply {
                setDataSource(file.absolutePath)
                setOnCompletionListener { it.release(); if (player === it) player = null }
                prepare()
                start()
            }
        } catch (t: Throwable) {
            toast("Playback failed • ${t.message}")
        }
    }

    private fun exportWav(uri: Uri) {
        if (!renderFile.isFile) return
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                contentResolver.openOutputStream(uri, "w")?.use { output -> renderFile.inputStream().use { it.copyTo(output) } }
                    ?: throw IllegalStateException("Cannot open export destination")
                withContext(Dispatchers.Main) { toast("Master WAV exported") }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) { toast("Export failed • ${t.message}") }
            }
        }
    }

    private fun releaseEngines() {
        pocketEngine?.release()
        piperEngine?.release()
        pocketEngine = null
        piperEngine = null
        activeThreads = -1
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    override fun onDestroy() {
        player?.release()
        releaseEngines()
        super.onDestroy()
    }

    private object StudioColors {
        val bg = Color(0xFF05070B)
        val surface = Color(0xFF101620)
        val surface2 = Color(0xFF161E2B)
        val deep = Color(0xFF090E16)
        val text = Color(0xFFF3F6FA)
        val muted = Color(0xFF8997AA)
        val accent = Color(0xFF62D8FF)
        val green = Color(0xFF69F0AE)
        val purple = Color(0xFFB99CFF)
        val red = Color(0xFFFF667A)
    }
}
