package com.nekospeak.tts.engine

import ai.onnxruntime.NodeInfo
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import android.content.Context
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.reflect.TypeToken
import com.nekospeak.tts.data.PrefsManager
import java.io.File
import java.nio.FloatBuffer
import java.nio.LongBuffer
import java.text.Normalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Local Malayalam VITS engine based on the ONNX export of facebook/mms-tts-mal.
 * The model is downloaded separately and runs entirely with ONNX Runtime Android.
 */
class MalayalamMmsEngine(private val context: Context) : TtsEngine {
    companion object {
        private const val TAG = "MalayalamMmsEngine"
        private const val MODEL_DIR = "malayalam"
    }

    private var env: OrtEnvironment? = null
    private var session: OrtSession? = null
    private var vocab: Map<String, Int> = emptyMap()
    private var padId: Int = 0
    private var unkId: Int = 0
    private var addBlank: Boolean = true
    private var sampleRate: Int = 16_000
    @Volatile private var initialized = false
    @Volatile private var stopRequested = false

    override suspend fun initialize(): Boolean = withContext(Dispatchers.IO) {
        try {
            val dir = File(context.filesDir, MODEL_DIR)
            val model = File(dir, "model.onnx")
            val vocabFile = File(dir, "vocab.json")
            val tokenizerFile = File(dir, "tokenizer_config.json")
            val configFile = File(dir, "config.json")
            if (!model.exists() || !vocabFile.exists() || !tokenizerFile.exists()) {
                Log.e(TAG, "Malayalam model files are not installed")
                return@withContext false
            }

            val gson = Gson()
            val vocabType = object : TypeToken<Map<String, Int>>() {}.type
            vocab = gson.fromJson(vocabFile.readText(), vocabType)
            val tokenizer = gson.fromJson(tokenizerFile.readText(), JsonObject::class.java)
            val padToken = tokenizer.get("pad_token")?.asString ?: vocab.keys.firstOrNull().orEmpty()
            val unkToken = tokenizer.get("unk_token")?.asString ?: "<unk>"
            addBlank = tokenizer.get("add_blank")?.asBoolean ?: true
            padId = vocab[padToken] ?: 0
            unkId = vocab[unkToken] ?: vocab["<unk>"] ?: padId

            if (configFile.exists()) {
                val config = gson.fromJson(configFile.readText(), JsonObject::class.java)
                sampleRate = config.get("sampling_rate")?.asInt ?: 16_000
            }

            env = OrtEnvironment.getEnvironment()
            val options = OrtSession.SessionOptions().apply {
                val threads = PrefsManager(context).cpuThreads.coerceIn(1, 6)
                setIntraOpNumThreads(threads)
                setInterOpNumThreads(1)
                setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
            }
            session = env!!.createSession(model.absolutePath, options)
            initialized = true
            true
        } catch (t: Throwable) {
            Log.e(TAG, "Failed to initialize Malayalam MMS engine", t)
            release()
            false
        }
    }

    override suspend fun generate(
        text: String,
        speed: Float,
        voice: String?,
        callback: (FloatArray) -> Unit
    ) = withContext(Dispatchers.Default) {
        val localSession = session ?: error("Malayalam model is not initialized")
        val localEnv = env ?: error("ONNX Runtime is not initialized")
        stopRequested = false

        val inputIds = tokenize(text)
        if (inputIds.isEmpty()) return@withContext
        val attention = LongArray(inputIds.size) { 1L }

        val prefs = context.getSharedPreferences("nekospeak_prefs", Context.MODE_PRIVATE)
        val noiseScale = prefs.getFloat("malayalam_noise_scale", 0.667f).coerceIn(0.1f, 1.2f)
        val durationNoise = prefs.getFloat("malayalam_duration_noise", 0.8f).coerceIn(0.1f, 1.5f)
        val lengthScale = (1f / speed.coerceIn(0.5f, 2.0f)).coerceIn(0.5f, 2.0f)

        val tensors = linkedMapOf<String, OnnxTensor>()
        try {
            for ((name, node) in localSession.inputInfo) {
                val lower = name.lowercase()
                val tensor = when {
                    lower.contains("input_ids") || lower == "x" -> OnnxTensor.createTensor(
                        localEnv,
                        LongBuffer.wrap(inputIds),
                        longArrayOf(1, inputIds.size.toLong())
                    )
                    lower.contains("attention_mask") || lower.contains("x_length") -> {
                        if (lower.contains("length")) {
                            OnnxTensor.createTensor(localEnv, LongBuffer.wrap(longArrayOf(inputIds.size.toLong())), longArrayOf(1))
                        } else {
                            OnnxTensor.createTensor(localEnv, LongBuffer.wrap(attention), longArrayOf(1, attention.size.toLong()))
                        }
                    }
                    lower.contains("speaker") || lower == "sid" -> OnnxTensor.createTensor(
                        localEnv,
                        LongBuffer.wrap(longArrayOf(0L)),
                        longArrayOf(1)
                    )
                    lower == "scales" || lower.contains("scale_values") -> createFloatTensorForNode(
                        localEnv,
                        node,
                        floatArrayOf(noiseScale, lengthScale, durationNoise)
                    )
                    lower.contains("noise_scale_w") || lower.contains("duration_noise") -> createFloatTensorForNode(localEnv, node, floatArrayOf(durationNoise))
                    lower.contains("noise_scale") -> createFloatTensorForNode(localEnv, node, floatArrayOf(noiseScale))
                    lower.contains("length_scale") -> createFloatTensorForNode(localEnv, node, floatArrayOf(lengthScale))
                    else -> throw IllegalStateException("Unsupported Malayalam model input: $name")
                }
                tensors[name] = tensor
            }

            localSession.run(tensors).use { result ->
                if (stopRequested) return@use
                val samples = flattenFloatOutput(result[0].value)
                if (samples.isNotEmpty()) callback(samples)
            }
        } finally {
            tensors.values.forEach { runCatching { it.close() } }
        }
    }

    private fun createFloatTensorForNode(env: OrtEnvironment, node: NodeInfo, values: FloatArray): OnnxTensor {
        val info = node.info as? TensorInfo
        val dimensions = info?.shape?.size ?: 1
        val shape = if (dimensions >= 2) longArrayOf(1, values.size.toLong()) else longArrayOf(values.size.toLong())
        return OnnxTensor.createTensor(env, FloatBuffer.wrap(values), shape)
    }

    private fun tokenize(rawText: String): LongArray {
        val normalized = Normalizer.normalize(rawText, Normalizer.Form.NFKC)
            .replace(Regex("\\s+"), " ")
            .trim()
        if (normalized.isEmpty()) return LongArray(0)

        val ids = ArrayList<Int>(normalized.length)
        normalized.forEach { ch ->
            val token = if (ch.isWhitespace()) {
                when {
                    vocab.containsKey("|") -> "|"
                    vocab.containsKey(" ") -> " "
                    else -> ch.toString()
                }
            } else ch.toString()
            ids += vocab[token] ?: unkId
        }

        if (!addBlank) return ids.map(Int::toLong).toLongArray()
        val withBlank = LongArray(ids.size * 2 + 1)
        var out = 0
        withBlank[out++] = padId.toLong()
        ids.forEach { id ->
            withBlank[out++] = id.toLong()
            withBlank[out++] = padId.toLong()
        }
        return withBlank
    }

    private fun flattenFloatOutput(value: Any?): FloatArray {
        return when (value) {
            null -> FloatArray(0)
            is FloatArray -> value
            is Array<*> -> {
                val pieces = value.map { flattenFloatOutput(it) }
                val total = pieces.sumOf { it.size }
                FloatArray(total).also { destination ->
                    var offset = 0
                    pieces.forEach { part ->
                        System.arraycopy(part, 0, destination, offset, part.size)
                        offset += part.size
                    }
                }
            }
            is java.nio.FloatBuffer -> FloatArray(value.remaining()).also { value.get(it) }
            else -> {
                Log.e(TAG, "Unsupported ONNX output type: ${value::class.java.name}")
                FloatArray(0)
            }
        }
    }

    override fun getSampleRate(): Int = sampleRate
    override fun getVoices(): List<String> = listOf("malayalam_natural")
    override fun isInitialized(): Boolean = initialized

    override fun stop() {
        stopRequested = true
    }

    override fun release() {
        initialized = false
        runCatching { session?.close() }
        session = null
        env = null
    }
}
