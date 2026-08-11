package com.genrobotics.pockettts

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import com.k2fsa.sherpa.onnx.GenerationConfig
import com.k2fsa.sherpa.onnx.GeneratedAudio
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsPocketModelConfig
import com.k2fsa.sherpa.onnx.WaveReader
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

class PocketEngine(private val modelDir: File, private var threads: Int = 2) {
    private var tts: OfflineTts? = null
    private val cancel = AtomicBoolean(false)

    fun initialize() {
        release()
        val pocket = OfflineTtsPocketModelConfig(
            lmFlow = File(modelDir, "lm_flow.int8.onnx").absolutePath,
            lmMain = File(modelDir, "lm_main.int8.onnx").absolutePath,
            encoder = File(modelDir, "encoder.onnx").absolutePath,
            decoder = File(modelDir, "decoder.int8.onnx").absolutePath,
            textConditioner = File(modelDir, "text_conditioner.onnx").absolutePath,
            vocabJson = File(modelDir, "vocab.json").absolutePath,
            tokenScoresJson = File(modelDir, "token_scores.json").absolutePath,
            voiceEmbeddingCacheCapacity = 12
        )
        val config = OfflineTtsConfig(
            model = OfflineTtsModelConfig(
                pocket = pocket,
                numThreads = threads.coerceIn(1, 4),
                debug = false,
                provider = "cpu"
            ),
            maxNumSentences = 1,
            silenceScale = 0.2f
        )
        tts = OfflineTts(config = config)
    }

    fun setThreads(value: Int) {
        val v = value.coerceIn(1, 4)
        if (v != threads) {
            threads = v
            initialize()
        }
    }

    fun isInitialized() = tts != null
    fun sampleRate() = tts?.sampleRate() ?: 24000
    fun cancelGeneration() { cancel.set(true) }

    fun generate(
        text: String,
        referenceWav: File,
        speed: Float,
        temperature: Float,
        steps: Int,
        seed: Int,
        silence: Float,
        livePlayback: Boolean,
        onChunk: (Int) -> Unit
    ): GeneratedAudio {
        val engine = tts ?: error("TTS engine is not initialized")
        val wave = WaveReader.readWave(referenceWav.absolutePath)
        require(wave.samples.isNotEmpty()) { "Reference WAV contains no audio" }
        cancel.set(false)

        val extra = linkedMapOf(
            "max_reference_audio_len" to "10",
            "temperature" to temperature.coerceIn(0.1f, 2.0f).toString()
        )
        if (seed >= 0) extra["seed"] = seed.toString()

        val cfg = GenerationConfig(
            silenceScale = silence.coerceIn(0f, 1f),
            speed = speed.coerceIn(0.5f, 2f),
            referenceAudio = wave.samples,
            referenceSampleRate = wave.sampleRate,
            numSteps = steps.coerceIn(1, 50),
            extra = extra
        )

        val track = if (livePlayback) makeAudioTrack(engine.sampleRate()) else null
        try {
            track?.play()
            var received = 0
            return engine.generateWithConfigAndCallback(text, cfg) { chunk ->
                if (cancel.get()) return@generateWithConfigAndCallback 0
                received += chunk.size
                onChunk(received)
                if (track != null && chunk.isNotEmpty()) {
                    track.write(chunk, 0, chunk.size, AudioTrack.WRITE_BLOCKING)
                }
                1
            }
        } finally {
            try { track?.stop() } catch (_: Exception) {}
            track?.release()
        }
    }

    private fun makeAudioTrack(sampleRate: Int): AudioTrack {
        val min = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_FLOAT
        ).coerceAtLeast(sampleRate / 2 * 4)
        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                    .setSampleRate(sampleRate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setBufferSizeInBytes(min)
            .build()
    }

    fun release() {
        tts?.release()
        tts = null
    }
}
