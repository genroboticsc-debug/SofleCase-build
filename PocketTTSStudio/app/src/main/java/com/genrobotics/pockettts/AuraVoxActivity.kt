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
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
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
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

class AuraVoxActivity : ComponentActivity() {
    private val modelManager by lazy { ModelManager(this) }
    private val prefs by lazy { getSharedPreferences("auravox", Context.MODE_PRIVATE) }
    private val nimClient = AuraNimClient()

    private var pocketEngine: PocketEngine? = null
    private var piperEngine: PiperEngine? = null
    private var activeThreads = -1
    private var player: MediaPlayer? = null

    private val renderFile by lazy { File(filesDir, "auravox/renders/master.wav").also { it.parentFile?.mkdirs() } }
    private val rawFile by lazy { File(filesDir, "auravox/renders/raw.wav").also { it.parentFile?.mkdirs() } }
    private val voicesDir by lazy { File(filesDir, "auravox/voices").also { it.mkdirs() } }

    private var selectedPackId by mutableStateOf("pocket_en")
    private var scriptText by mutableStateOf("Create or paste a script in AuraVox Studio.")
    private var status by mutableStateOf("AURAVOX CORE • IDLE")
    private var engineReady by mutableStateOf(false)
    private var generating by mutableStateOf(false)
    private var streamedSamples by mutableStateOf(0)
    private var waveform by mutableStateOf<FloatArray?>(null)
    private var outputRate by mutableStateOf(24000)
    private var lastRawAudio: SynthAudio? = null
    private var referenceFile: File? = null
    private var voiceName by mutableStateOf("No clone reference")
    private var installPackId by mutableStateOf<String?>(null)
    private var installProgress by mutableStateOf(0)
    private var installMessage by mutableStateOf("")
    private var voiceProfiles by mutableStateOf<List<File>>(emptyList())

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
    private var lastPeakDb by mutableStateOf(-120.0)
    private var lastRmsDb by mutableStateOf(-120.0)
    private var lastRtf by mutableStateOf(0.0)

    private var nvidiaKey by mutableStateOf("")
    private var nexusPrompt by mutableStateOf("Create a cinematic multilingual voice scene with natural Malayalam and English dialogue.")
    private var nexusGenerating by mutableStateOf(false)
    private var nexusModel by mutableStateOf("Not connected")
    private var nexusTitle by mutableStateOf("AuraVox Project")
    private var nexusSummary by mutableStateOf("Use the Nexus to generate scripts and character casting with NVIDIA NIM.")
    private var nexusCharacters by mutableStateOf<List<String>>(emptyList())

    private val exportLauncher = registerForActivityResult(ActivityResultContracts.CreateDocument("audio/wav")) { uri ->
        if (uri != null) exportMaster(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        selectedPackId = prefs.getString("pack", "pocket_en") ?: "pocket_en"
        threads = prefs.getFloat("threads", 2f).coerceIn(1f, 4f)
        livePlayback = prefs.getBoolean("live", true)
        refreshProfiles()
        val pack = ModelCatalog.byId(selectedPackId)
        scriptText = pack.sampleText
        selectPack(pack, keepScript = true)
        setContent { AuraVoxApp() }
    }

    private fun selectedPack() = ModelCatalog.byId(selectedPackId)

    private fun selectPack(pack: ModelPack, keepScript: Boolean = false) {
        selectedPackId = pack.id
        prefs.edit().putString("pack", pack.id).apply()
        speakerId = 0f
        if (!keepScript) scriptText = pack.sampleText
        releaseEngines()
        engineReady = false

        if (!modelManager.isReady(pack)) {
            status = "MODEL VAULT • ${pack.voiceName} NOT INSTALLED"
            return
        }
        if (pack.engine == EngineKind.POCKET && (referenceFile == null || referenceFile?.isFile != true)) {
            val f = modelManager.defaultVoice(pack)
            if (f.isFile) {
                referenceFile = f
                voiceName = "Bria • bundled reference"
            }
        }
        initializeEngine(pack)
    }

    private fun initializeEngine(pack: ModelPack) {
        releaseEngines()
        engineReady = false
        status = "LOADING • ${pack.voiceName}"
        val requestedThreads = threads.toInt()
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                when (pack.engine) {
                    EngineKind.POCKET -> {
                        val engine = PocketEngine(modelManager.dir(pack), requestedThreads)
                        engine.initialize()
                        pocketEngine = engine
                        outputRate = engine.sampleRate()
                    }
                    EngineKind.PIPER -> {
                        val engine = PiperEngine(modelManager.dir(pack), pack, requestedThreads)
                        engine.initialize()
                        piperEngine = engine
                        outputRate = engine.sampleRate()
                    }
                }
                activeThreads = requestedThreads
                withContext(Dispatchers.Main) {
                    engineReady = true
                    status = "READY • ${engineLabel(pack)} • ${outputRate}Hz • ${requestedThreads}T"
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) {
                    engineReady = false
                    status = "ENGINE ERROR • ${t.message ?: t.javaClass.simpleName}"
                }
            }
        }
    }

    private fun engineLabel(pack: ModelPack) = if (pack.engine == EngineKind.POCKET) "KYUTAI POCKETTTS" else "SHERPA / PIPER"

    private fun installPack(pack: ModelPack) {
        if (installPackId != null) return
        installPackId = pack.id
        installProgress = 0
        installMessage = "Preparing ${pack.displayName}"
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
                installMessage = "Install failed • ${t.message ?: t.javaClass.simpleName}"
                withContext(Dispatchers.Main) { toast(installMessage) }
            } finally {
                installPackId = null
            }
        }
    }

    private fun generateNexus() {
        if (nexusGenerating) return
        if (nvidiaKey.isBlank()) {
            toast("Enter your NVIDIA API key in Nexus")
            return
        }
        if (nexusPrompt.isBlank()) return
        nexusGenerating = true
        nexusModel = "Routing NIM ring…"
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val result = nimClient.generate(nvidiaKey, nexusPrompt)
                withContext(Dispatchers.Main) {
                    nexusTitle = result.title
                    nexusSummary = result.summary
                    nexusCharacters = result.characters
                    nexusModel = result.modelUsed
                    scriptText = result.scriptText
                    status = "NEXUS READY • SCRIPT ROUTED TO STUDIO"
                    nexusGenerating = false
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) {
                    nexusModel = "NIM error"
                    status = "NEXUS ERROR • ${t.message ?: t.javaClass.simpleName}"
                    nexusGenerating = false
                    toast(status)
                }
            }
        }
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
        if (generating) return
        if (scriptText.isBlank()) { toast("Enter a script"); return }
        if (!modelManager.isReady(pack)) { toast("Install ${pack.voiceName} in Models"); return }
        if (pack.engine == EngineKind.POCKET && (ref == null || !ref.isFile)) { toast("Import a WAV clone reference"); return }
        if (!engineReady || activeThreads != threads.toInt()) {
            initializeEngine(pack)
            toast("Engine is loading")
            return
        }

        val text = scriptText
        val refCaptured = ref
        val started = System.nanoTime()
        generating = true
        streamedSamples = 0
        waveform = null
        status = "RENDERING • ${pack.voiceName}"
        val power = getSystemService(POWER_SERVICE) as PowerManager
        val wake = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AuraVox:Render")
        wake.acquire(10 * 60 * 1000L)

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val raw = when (pack.engine) {
                    EngineKind.POCKET -> pocketEngine!!.generate(
                        text = text,
                        referenceWav = refCaptured!!,
                        speed = speed,
                        temperature = temperature,
                        steps = steps.toInt(),
                        seed = seedText.toIntOrNull() ?: -1,
                        silence = silence,
                        livePlayback = livePlayback
                    ) { count -> runOnUiThread { streamedSamples = count } }
                    EngineKind.PIPER -> piperEngine!!.generate(
                        text = text,
                        speed = speed,
                        silence = silence,
                        speakerId = speakerId.toInt(),
                        livePlayback = livePlayback
                    ) { count -> runOnUiThread { streamedSamples = count } }
                }
                if (raw.samples.isEmpty()) {
                    withContext(Dispatchers.Main) { generating = false; status = "RENDER CANCELLED" }
                    return@launch
                }
                lastRawAudio = raw
                raw.save(rawFile.absolutePath)
                val mastered = StudioAudio.process(raw, currentMastering())
                check(mastered.save(renderFile.absolutePath)) { "Could not save master WAV" }
                val elapsed = (System.nanoTime() - started) / 1_000_000_000.0
                val rtf = elapsed / max(mastered.durationSeconds, 0.001)
                withContext(Dispatchers.Main) {
                    waveform = mastered.samples
                    outputRate = mastered.sampleRate
                    lastPeakDb = StudioAudio.peakDb(mastered.samples)
                    lastRmsDb = StudioAudio.rmsDb(mastered.samples)
                    lastRtf = rtf
                    status = "MASTER READY • ${String.format("%.2f", mastered.durationSeconds)}s • RTF ${String.format("%.2f", rtf)}"
                    generating = false
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) {
                    generating = false
                    status = "RENDER ERROR • ${t.message ?: t.javaClass.simpleName}"
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
        status = "CANCELLING…"
    }

    private fun remaster() {
        val raw = lastRawAudio ?: run { toast("Render a take first"); return }
        lifecycleScope.launch(Dispatchers.Default) {
            val mastered = StudioAudio.process(raw, currentMastering())
            mastered.save(renderFile.absolutePath)
            withContext(Dispatchers.Main) {
                waveform = mastered.samples
                lastPeakDb = StudioAudio.peakDb(mastered.samples)
                lastRmsDb = StudioAudio.rmsDb(mastered.samples)
                status = "MASTER CHAIN REAPPLIED"
            }
        }
    }

    @Composable
    private fun AuraVoxApp() {
        val c = AuraColors
        MaterialTheme(colors = darkColors(primary = c.cyan, secondary = c.violet, background = c.bg, surface = c.panel, onSurface = c.text)) {
            Box(
                Modifier.fillMaxSize().background(
                    Brush.radialGradient(
                        colors = listOf(Color(0xFF10253A), c.bg),
                        radius = 1300f
                    )
                )
            ) {
                var tab by remember { mutableStateOf(0) }
                Column(Modifier.fillMaxSize()) {
                    AuraHeader()
                    ScrollableTabRow(
                        selectedTabIndex = tab,
                        backgroundColor = c.panel.copy(alpha = .95f),
                        contentColor = c.cyan,
                        edgePadding = 7.dp
                    ) {
                        listOf("NEXUS", "STUDIO", "VOICES", "MODELS", "MASTER", "SYSTEM").forEachIndexed { index, label ->
                            Tab(selected = tab == index, onClick = { tab = index }, text = {
                                Text(label, fontSize = 10.sp, fontWeight = if (tab == index) FontWeight.Black else FontWeight.Normal)
                            })
                        }
                    }
                    when (tab) {
                        0 -> NexusScreen { tab = 1 }
                        1 -> StudioScreen { tab = 3 }
                        2 -> VoicesScreen()
                        3 -> ModelsScreen()
                        4 -> MasterScreen()
                        else -> SystemScreen()
                    }
                }
            }
        }
    }

    @Composable
    private fun AuraHeader() {
        val c = AuraColors
        val pack = selectedPack()
        Row(
            Modifier.fillMaxWidth().background(c.panel.copy(alpha = .92f)).padding(horizontal = 15.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text("AURAVOX STUDIO", fontSize = 20.sp, fontWeight = FontWeight.Black, letterSpacing = 1.1.sp)
                Text("NEURAL VOICE PRODUCTION MATRIX", color = c.muted, fontSize = 9.sp, letterSpacing = 1.0.sp)
            }
            Column(horizontalAlignment = Alignment.End) {
                AuraBadge(if (engineReady) "● CORE READY" else "● CORE IDLE", if (engineReady) c.green else c.gold)
                Spacer(Modifier.height(3.dp))
                Text(pack.nativeLanguageName, color = c.muted, fontSize = 9.sp)
            }
        }
    }

    @Composable
    private fun NexusScreen(openStudio: () -> Unit) {
        val c = AuraColors
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            GlassCard(highlight = true) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("THE NEXUS", color = c.cyan, fontSize = 18.sp, fontWeight = FontWeight.Black)
                        Text("NVIDIA NIM • SCRIPT ARCHITECT • CASTING DIRECTOR", color = c.muted, fontSize = 9.sp, letterSpacing = .7.sp)
                    }
                    AuraBadge(if (nexusGenerating) "ROUTING" else "CLOUD", c.violet)
                }
                Spacer(Modifier.height(10.dp))
                NexusVisual(nexusCharacters, nexusGenerating)
            }

            GlassCard {
                Text("NVIDIA API", color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                OutlinedTextField(
                    value = nvidiaKey,
                    onValueChange = { nvidiaKey = it.trim() },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("NVIDIA API key (session only)") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation()
                )
                Text("The key is held only in this running activity and is not written to SharedPreferences.", color = c.muted, fontSize = 9.sp)
            }

            GlassCard {
                Text("CREATIVE BRIEF", color = c.violet, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                OutlinedTextField(
                    value = nexusPrompt,
                    onValueChange = { nexusPrompt = it },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 145.dp),
                    label = { Text("Story, cast, languages, emotion, structure…") },
                    maxLines = 16
                )
                Spacer(Modifier.height(6.dp))
                if (!nexusGenerating) {
                    Button(onClick = { generateNexus() }, modifier = Modifier.fillMaxWidth().height(48.dp)) {
                        Text("GENERATE SCRIPT + CAST", fontWeight = FontWeight.Black)
                    }
                } else {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Spacer(Modifier.height(7.dp))
                    OutlinedButton(onClick = { nimClient.cancel() }, modifier = Modifier.fillMaxWidth()) { Text("CANCEL NEXUS") }
                }
            }

            GlassCard(highlight = nexusCharacters.isNotEmpty()) {
                Text(nexusTitle, fontSize = 17.sp, fontWeight = FontWeight.Black)
                Text(nexusSummary, color = c.muted, fontSize = 11.sp)
                Spacer(Modifier.height(8.dp))
                Text("MODEL • $nexusModel", color = c.cyan, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                if (nexusCharacters.isNotEmpty()) {
                    Spacer(Modifier.height(9.dp))
                    Text("CAST MATRIX", color = c.gold, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    nexusCharacters.take(10).forEach { character ->
                        Text("◈ $character", color = c.text, fontSize = 11.sp, modifier = Modifier.padding(vertical = 3.dp))
                    }
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = openStudio, modifier = Modifier.fillMaxWidth()) { Text("OPEN SCRIPT IN STUDIO") }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun NexusVisual(characters: List<String>, active: Boolean) {
        val c = AuraColors
        val names = if (characters.isEmpty()) listOf("NEMOTRON", "SCRIPT", "CAST", "VOICE") else characters.take(6).map { it.substringBefore('—').trim().take(12) }
        Canvas(Modifier.fillMaxWidth().height(170.dp).background(c.deep, RoundedCornerShape(18.dp))) {
            val center = Offset(size.width / 2f, size.height / 2f)
            val radius = min(size.width, size.height) * .34f
            val positions = names.indices.map { i ->
                val a = (i.toFloat() / names.size.toFloat()) * (Math.PI * 2.0).toFloat() - 1.1f
                Offset(center.x + cos(a) * radius, center.y + sin(a) * radius)
            }
            positions.forEachIndexed { i, p ->
                val next = positions[(i + 1) % positions.size]
                drawLine(if (active) c.cyan.copy(alpha = .78f) else c.cyan.copy(alpha = .2f), p, next, strokeWidth = if (active) 2.5f else 1.2f)
                drawCircle(if (i % 2 == 0) c.violet else c.cyan, radius = if (active) 11f else 8f, center = p)
                drawCircle(Color.White.copy(alpha = .35f), radius = 3f, center = p)
            }
            drawCircle(c.gold.copy(alpha = if (active) .85f else .35f), radius = if (active) 14f else 10f, center = center)
        }
    }

    @Composable
    private fun StudioScreen(openModels: () -> Unit) {
        val c = AuraColors
        val pack = selectedPack()
        val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? -> if (uri != null) importReference(uri) }
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            GlassCard(highlight = true) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("MIXDECK / VOICE TRACK", color = c.cyan, fontSize = 17.sp, fontWeight = FontWeight.Black)
                        Text(pack.displayName, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        Text(engineLabel(pack), color = if (pack.engine == EngineKind.POCKET) c.violet else c.green, fontSize = 9.sp)
                    }
                    AuraBadge(if (pack.cloneVoice) "CLONE" else "LOCAL", if (pack.cloneVoice) c.violet else c.green)
                }
                Spacer(Modifier.height(7.dp))
                Text(status, color = if (engineReady) c.green else c.gold, fontSize = 10.sp)
            }

            Text("LANGUAGE / VOICE ROUTING", color = c.muted, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = .8.sp)
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                ModelCatalog.packs.forEach { p ->
                    ChoiceChip("${p.nativeLanguageName} • ${p.voiceName}", p.id == pack.id) { selectPack(p) }
                }
            }

            GlassCard {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("SCRIPT CHANNEL", color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    Text("${scriptText.length} chars", color = c.muted, fontSize = 9.sp)
                }
                OutlinedTextField(
                    value = scriptText,
                    onValueChange = { scriptText = it },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 190.dp),
                    label = { Text("Dialogue / narration") },
                    maxLines = 22
                )
                Row {
                    TextButton(onClick = { scriptText = pack.sampleText }) { Text("SAMPLE") }
                    TextButton(onClick = { scriptText = "" }) { Text("CLEAR") }
                }
            }

            if (pack.engine == EngineKind.POCKET) {
                GlassCard {
                    Text("VOICE CLONE INPUT", color = c.violet, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    Text(voiceName, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("Use only a voice you own or have permission to clone.", color = c.muted, fontSize = 9.sp)
                    Spacer(Modifier.height(7.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { picker.launch(arrayOf("audio/wav", "audio/x-wav", "audio/wave")) }, modifier = Modifier.weight(1f)) { Text("IMPORT WAV") }
                        OutlinedButton(onClick = { useDefaultReference() }, modifier = Modifier.weight(1f), enabled = modelManager.isReady(pack)) { Text("BRIA") }
                    }
                }
            }

            GlassCard {
                Text("ULTRA SYNTHESIS CONTROLS", color = c.gold, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                SliderControl("Speed", speed, .5f..2f, "%.2fx") { speed = it }
                SliderControl("Pause / silence", silence, 0f..1f, "%.2f") { silence = it }
                if (pack.engine == EngineKind.POCKET) {
                    SliderControl("Temperature", temperature, .1f..2f, "%.2f") { temperature = it }
                    SliderControl("Sampling steps", steps, 1f..30f, "%.0f") { steps = it }
                    OutlinedTextField(value = seedText, onValueChange = { seedText = it.filter { ch -> ch == '-' || ch.isDigit() }.take(11) }, label = { Text("Seed (-1 random)") }, modifier = Modifier.fillMaxWidth())
                }
                if (pack.speakers > 1) SliderControl("Speaker ID", speakerId, 0f..(pack.speakers - 1).toFloat(), "%.0f") { speakerId = it }
            }

            GlassCard(highlight = true) {
                Text("LIVE MATRIX / MASTER", color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                val samples = waveform
                if (samples != null && samples.isNotEmpty()) {
                    Waveform(samples)
                    Spacer(Modifier.height(7.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        MeterPill("PK ${String.format("%.1f", lastPeakDb)}")
                        MeterPill("RMS ${String.format("%.1f", lastRmsDb)}")
                        MeterPill("RTF ${String.format("%.2f", lastRtf)}")
                    }
                } else {
                    Box(Modifier.fillMaxWidth().height(104.dp).background(c.deep, RoundedCornerShape(16.dp)), contentAlignment = Alignment.Center) {
                        Text(if (generating) "STREAMING • $streamedSamples samples" else "AWAITING AUDIO", color = c.muted, fontSize = 10.sp)
                    }
                }
                Spacer(Modifier.height(9.dp))
                if (!modelManager.isReady(pack)) {
                    Button(onClick = openModels, modifier = Modifier.fillMaxWidth()) { Text("INSTALL MODEL") }
                } else if (generating) {
                    Button(onClick = { cancelRender() }, colors = ButtonDefaults.buttonColors(backgroundColor = c.red), modifier = Modifier.fillMaxWidth().height(48.dp)) { Text("STOP RENDER", fontWeight = FontWeight.Black) }
                } else {
                    Button(onClick = { renderSpeech() }, enabled = engineReady, modifier = Modifier.fillMaxWidth().height(50.dp)) { Text(if (engineReady) "RENDER MASTER" else "LOADING CORE…", fontWeight = FontWeight.Black) }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { playFile(renderFile) }, enabled = renderFile.isFile && !generating, modifier = Modifier.weight(1f)) { Text("PLAY") }
                    OutlinedButton(onClick = { exportLauncher.launch("AuraVox-${System.currentTimeMillis()}.wav") }, enabled = renderFile.isFile && !generating, modifier = Modifier.weight(1f)) { Text("EXPORT WAV") }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun VoicesScreen() {
        val c = AuraColors
        val pack = selectedPack()
        val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? -> if (uri != null) importReference(uri) }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            GlassCard(highlight = true) {
                Text("VOICE LAB", color = c.violet, fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("Clone references, regional voices and local neural profiles", color = c.muted, fontSize = 10.sp)
            }
            GlassCard {
                Text("POCKETTTS ZERO-SHOT CLONE", color = c.violet, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                Text(voiceName, fontWeight = FontWeight.Bold)
                Text("Import a clean WAV reference from a voice you have permission to use.", color = c.muted, fontSize = 9.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { picker.launch(arrayOf("audio/wav", "audio/x-wav", "audio/wave")) }, modifier = Modifier.weight(1f)) { Text("IMPORT VOICE") }
                    OutlinedButton(onClick = { useDefaultReference() }, modifier = Modifier.weight(1f), enabled = modelManager.isReady(ModelCatalog.byId("pocket_en"))) { Text("BRIA") }
                }
            }
            if (voiceProfiles.isNotEmpty()) {
                Text("LOCAL CLONE PROFILES", color = c.muted, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                voiceProfiles.forEach { file ->
                    GlassCard {
                        Row(Modifier.fillMaxWidth().clickable {
                            referenceFile = file
                            voiceName = file.nameWithoutExtension
                            if (pack.engine == EngineKind.POCKET) status = "VOICE PROFILE • ${file.nameWithoutExtension}"
                        }, verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(file.nameWithoutExtension, fontWeight = FontWeight.Bold)
                                Text(modelManager.formatBytes(file.length()), color = c.muted, fontSize = 9.sp)
                            }
                            AuraBadge("USE", c.cyan)
                        }
                    }
                }
            }
            Text("REGIONAL VOICE MATRIX", color = c.muted, fontSize = 9.sp, fontWeight = FontWeight.Bold)
            ModelCatalog.packs.filter { it.engine == EngineKind.PIPER }.forEach { p ->
                GlassCard {
                    Row(Modifier.fillMaxWidth().clickable { selectPack(p) }, verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${p.nativeLanguageName} • ${p.voiceName}", fontWeight = FontWeight.Black)
                            Text(p.quality, color = c.muted, fontSize = 9.sp)
                        }
                        AuraBadge(if (modelManager.isReady(p)) "INSTALLED" else "PACK", c.green)
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun ModelsScreen() {
        val c = AuraColors
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            GlassCard(highlight = true) {
                Text("MODEL VAULT", color = c.cyan, fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("${modelManager.installedPacks().size}/${ModelCatalog.packs.size} installed • ${modelManager.formatBytes(modelManager.totalInstalledBytes())}", color = c.muted, fontSize = 10.sp)
                if (installPackId != null) {
                    LinearProgressIndicator(installProgress / 100f, Modifier.fillMaxWidth())
                    Text(installMessage, color = c.cyan, fontSize = 9.sp)
                }
            }
            ModelCatalog.packs.forEach { p ->
                val ready = modelManager.isReady(p)
                GlassCard {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(p.displayName, fontWeight = FontWeight.Black)
                            Text("${engineLabel(p)} • ${p.quality}", color = if (p.engine == EngineKind.POCKET) c.violet else c.green, fontSize = 9.sp)
                        }
                        AuraBadge(if (ready) "VERIFIED" else "OFFLINE", if (ready) c.green else c.gold)
                    }
                    Text(p.description, color = c.muted, fontSize = 10.sp)
                    if (installPackId == p.id) {
                        LinearProgressIndicator(installProgress / 100f, Modifier.fillMaxWidth())
                        Text(installMessage, color = c.cyan, fontSize = 9.sp)
                    } else if (!ready) {
                        Button(onClick = { installPack(p) }, enabled = installPackId == null, modifier = Modifier.fillMaxWidth()) { Text("DOWNLOAD + VERIFY") }
                    } else {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { selectPack(p) }, modifier = Modifier.weight(1f)) { Text(if (p.id == selectedPackId) "ACTIVE" else "USE") }
                            OutlinedButton(onClick = {
                                if (p.id == selectedPackId) { releaseEngines(); engineReady = false }
                                modelManager.delete(p)
                                status = "MODEL REMOVED • ${p.voiceName}"
                            }, enabled = !generating && installPackId == null, modifier = Modifier.weight(1f)) { Text("REMOVE") }
                        }
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun MasterScreen() {
        val c = AuraColors
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            GlassCard(highlight = true) {
                Text("MASTER BUS", color = c.gold, fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("Non-destructive cleanup, gain staging and export protection", color = c.muted, fontSize = 10.sp)
            }
            GlassCard {
                Text("CLEANUP", color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                ToggleRow("DC removal", "Remove measured waveform offset", masterDc) { masterDc = it }
                ToggleRow("Silence trim", "Trim low-level edges with guard", masterTrim) { masterTrim = it }
                ToggleRow("Peak normalize", "Normalize to target ceiling", masterNormalize) { masterNormalize = it }
            }
            GlassCard {
                Text("DYNAMICS", color = c.gold, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                ToggleRow("Smooth limiter", "Soft saturation and hard export protection", masterLimiter) { masterLimiter = it }
                SliderControl("Target peak", masterPeakTarget, -6f..-.2f, "%.1f dBFS") { masterPeakTarget = it }
                SliderControl("Output gain", masterGain, -12f..12f, "%+.1f dB") { masterGain = it }
                SliderControl("Edge fade", masterFadeMs, 0f..50f, "%.0f ms") { masterFadeMs = it }
                Button(onClick = { remaster() }, enabled = lastRawAudio != null && !generating, modifier = Modifier.fillMaxWidth()) { Text("REMASTER LAST RAW TAKE") }
            }
            GlassCard {
                Text("ANALYSIS", color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                KeyValue("Peak", "${String.format("%.1f", lastPeakDb)} dBFS")
                KeyValue("RMS", "${String.format("%.1f", lastRmsDb)} dBFS")
                KeyValue("RTF", String.format("%.2f", lastRtf))
                KeyValue("Output", "$outputRate Hz")
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun SystemScreen() {
        val c = AuraColors
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            GlassCard(highlight = true) {
                Text("SYSTEM MATRIX", color = c.cyan, fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("Mobile-local inference telemetry and runtime controls", color = c.muted, fontSize = 10.sp)
            }
            GlassCard {
                Text("PERFORMANCE", color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                SliderControl("CPU threads", threads, 1f..4f, "%.0f") {
                    threads = it
                    prefs.edit().putFloat("threads", it).apply()
                    if (activeThreads != it.toInt()) engineReady = false
                }
                ToggleRow("Live playback", "Stream audio while local inference runs", livePlayback) {
                    livePlayback = it
                    prefs.edit().putBoolean("live", it).apply()
                }
                if (!engineReady && modelManager.isReady(selectedPack())) {
                    OutlinedButton(onClick = { initializeEngine(selectedPack()) }, modifier = Modifier.fillMaxWidth()) { Text("RELOAD ENGINE") }
                }
            }
            GlassCard {
                Text("DEVICE", color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                KeyValue("ABI", android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
                KeyValue("CPU cores", Runtime.getRuntime().availableProcessors().toString())
                KeyValue("Android", "${android.os.Build.VERSION.RELEASE} / API ${android.os.Build.VERSION.SDK_INT}")
                KeyValue("Models", modelManager.formatBytes(modelManager.totalInstalledBytes()))
                KeyValue("Package", packageName)
            }
            GlassCard {
                Text("PRIVACY BOUNDARY", color = c.green, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                Text("Local voice synthesis, reference audio, renders and mastering stay on-device. Nexus sends only the creative text prompt to NVIDIA when you explicitly press Generate. The NVIDIA key is session-only.", color = c.muted, fontSize = 10.sp)
            }
            Spacer(Modifier.height(18.dp))
        }
    }

    @Composable
    private fun GlassCard(highlight: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
        val c = AuraColors
        Card(
            backgroundColor = if (highlight) c.panel2 else c.panel,
            shape = RoundedCornerShape(20.dp),
            elevation = 0.dp,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp), content = content)
        }
    }

    @Composable
    private fun ChoiceChip(label: String, selected: Boolean, onClick: () -> Unit) {
        val c = AuraColors
        Surface(color = if (selected) c.cyan.copy(alpha = .18f) else c.panel2, shape = RoundedCornerShape(18.dp), modifier = Modifier.clickable(onClick = onClick)) {
            Text(label, color = if (selected) c.cyan else c.text, fontSize = 10.sp, fontWeight = if (selected) FontWeight.Black else FontWeight.Medium, modifier = Modifier.padding(horizontal = 11.dp, vertical = 8.dp))
        }
    }

    @Composable
    private fun AuraBadge(text: String, color: Color) {
        Surface(color = color.copy(alpha = .12f), shape = RoundedCornerShape(18.dp)) {
            Text(text, color = color, fontSize = 9.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp))
        }
    }

    @Composable
    private fun MeterPill(text: String) {
        val c = AuraColors
        Surface(color = c.deep, shape = RoundedCornerShape(12.dp)) {
            Text(text, color = c.muted, fontSize = 9.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp))
        }
    }

    @Composable
    private fun SliderControl(label: String, value: Float, range: ClosedFloatingPointRange<Float>, format: String, onChange: (Float) -> Unit) {
        val c = AuraColors
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(label, modifier = Modifier.weight(1f), fontSize = 11.sp)
            Text(String.format(format, value), color = c.cyan, fontSize = 10.sp, fontWeight = FontWeight.Black)
        }
        Slider(value = value.coerceIn(range.start, range.endInclusive), onValueChange = onChange, valueRange = range)
    }

    @Composable
    private fun ToggleRow(title: String, subtitle: String, checked: Boolean, onChange: (Boolean) -> Unit) {
        val c = AuraColors
        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Text(subtitle, color = c.muted, fontSize = 9.sp)
            }
            Switch(checked = checked, onCheckedChange = onChange)
        }
    }

    @Composable
    private fun KeyValue(key: String, value: String) {
        val c = AuraColors
        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
            Text(key, color = c.muted, modifier = Modifier.weight(1f), fontSize = 10.sp)
            Text(value, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        }
    }

    @Composable
    private fun Waveform(samples: FloatArray) {
        val c = AuraColors
        Canvas(Modifier.fillMaxWidth().height(112.dp).background(c.deep, RoundedCornerShape(16.dp)).padding(8.dp)) {
            if (samples.isEmpty()) return@Canvas
            val mid = size.height / 2f
            val columns = max(1, size.width.toInt())
            val stride = max(1, samples.size / columns)
            var x = 0
            var index = 0
            while (x < columns && index < samples.size) {
                val end = min(index + stride, samples.size)
                var peak = 0f
                var i = index
                while (i < end) { peak = max(peak, abs(samples[i])); i++ }
                val amp = peak.coerceIn(0f, 1f) * size.height * .44f
                val color = if (x % 7 == 0) c.violet else c.cyan
                drawLine(color, Offset(x.toFloat(), mid - amp), Offset(x.toFloat(), mid + amp), strokeWidth = 1.5f, cap = StrokeCap.Round)
                index = end
                x++
            }
            drawLine(c.muted.copy(alpha = .18f), Offset(0f, mid), Offset(size.width, mid), strokeWidth = 1f)
        }
    }

    private fun importReference(uri: Uri) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val source = queryName(uri).ifBlank { "voice.wav" }
                val clean = source.substringBeforeLast('.').replace(Regex("[^A-Za-z0-9_-]+"), "_").take(48).ifBlank { "voice" }
                val target = File(voicesDir, "${clean}_${System.currentTimeMillis()}.wav")
                contentResolver.openInputStream(uri)?.use { input -> FileOutputStream(target).use { output -> input.copyTo(output) } }
                    ?: throw IllegalStateException("Cannot read selected file")
                require(target.length() > 44) { "Selected WAV is empty" }
                withContext(Dispatchers.Main) {
                    referenceFile = target
                    voiceName = clean
                    refreshProfiles()
                    status = "VOICE IMPORTED • $clean"
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) { toast("Voice import failed • ${t.message}") }
            }
        }
    }

    private fun useDefaultReference() {
        val pack = ModelCatalog.byId("pocket_en")
        val file = modelManager.defaultVoice(pack)
        if (file.isFile) {
            referenceFile = file
            voiceName = "Bria • bundled reference"
            status = "DEFAULT POCKETTTS REFERENCE"
        } else toast("Install PocketTTS first")
    }

    private fun refreshProfiles() {
        voicesDir.mkdirs()
        voiceProfiles = voicesDir.listFiles()?.filter { it.isFile && it.extension.equals("wav", true) }?.sortedByDescending { it.lastModified() } ?: emptyList()
    }

    private fun queryName(uri: Uri): String {
        var result = ""
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor -> if (cursor.moveToFirst()) result = cursor.getString(0) ?: "" }
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
        } catch (t: Throwable) { toast("Playback failed • ${t.message}") }
    }

    private fun exportMaster(uri: Uri) {
        if (!renderFile.isFile) return
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                contentResolver.openOutputStream(uri, "w")?.use { output -> renderFile.inputStream().use { it.copyTo(output) } }
                    ?: throw IllegalStateException("Cannot open export destination")
                withContext(Dispatchers.Main) { toast("AuraVox master exported") }
            } catch (t: Throwable) { withContext(Dispatchers.Main) { toast("Export failed • ${t.message}") } }
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
        nimClient.cancel()
        player?.release()
        releaseEngines()
        super.onDestroy()
    }

    private object AuraColors {
        val bg = Color(0xFF050608)
        val panel = Color(0xFF0F141D)
        val panel2 = Color(0xFF151D29)
        val deep = Color(0xFF080C12)
        val text = Color(0xFFF0F7FB)
        val muted = Color(0xFF8A92A6)
        val cyan = Color(0xFF00F3FF)
        val violet = Color(0xFFBD00FF)
        val gold = Color(0xFFFFB800)
        val green = Color(0xFF4DFFB8)
        val red = Color(0xFFFF4D7D)
    }
}
