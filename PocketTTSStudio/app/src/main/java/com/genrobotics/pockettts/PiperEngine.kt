package com.genrobotics.pockettts

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import com.k2fsa.sherpa.onnx.GenerationConfig
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

class PiperEngine(
    private val modelDir: File,
    private val pack: ModelPack,
    private val threads: Int = 2
) {
    private var tts: OfflineTts? = null
    private val cancel = AtomicBoolean(false)

    fun initialize() {
        release()
        require(pack.engine == EngineKind.PIPER) { "PiperEngine requires a Piper/VITS model pack" }
        val vits = OfflineTtsVitsModelConfig(
            model = File(modelDir, pack.modelFile).absolutePath,
            tokens = File(modelDir, "tokens.txt").absolutePath,
            dataDir = File(modelDir, "espeak-ng-data").absolutePath,
            lexicon = "",
            noiseScale = 0.667f,
            noiseScaleW = 0.8f,
            lengthScale = 1.0f
        )
        val config = OfflineTtsConfig(
            model = OfflineTtsModelConfig(
                vits = vits,
                numThreads = threads.coerceIn(1, 4),
                debug = false,
                provider = "cpu"
            ),
            maxNumSentences = 1,
            silenceScale = 0.2f
        )
        tts = OfflineTts(config = config)
    }

    fun sampleRate() = tts?.sampleRate() ?: pack.sampleRateHint
    fun numSpeakers() = tts?.numSpeakers() ?: pack.speakers
    fun cancelGeneration() { cancel.set(true) }

    fun generate(
        text: String,
        speed: Float,
        silence: Float,
        speakerId: Int,
        livePlayback: Boolean,
        onChunk: (Int) -> Unit
    ): SynthAudio {
        val engine = tts ?: error("Voice engine is not initialized")
        cancel.set(false)
        val cfg = GenerationConfig(
            silenceScale = silence.coerceIn(0f, 1f),
            speed = speed.coerceIn(0.5f, 2.0f),
            sid = speakerId.coerceIn(0, (numSpeakers() - 1).coerceAtLeast(0))
        )
        val sr = engine.sampleRate()
        val track = if (livePlayback) makeAudioTrack(sr) else null
        val chunks = ArrayList<FloatArray>(96)
        var received = 0
        try {
            track?.play()
            engine.generateWithConfigAndCallback(text, cfg) { chunk ->
                if (cancel.get()) return@generateWithConfigAndCallback 0
                if (chunk.isNotEmpty()) {
                    chunks.add(chunk.copyOf())
                    received += chunk.size
                    onChunk(received)
                    track?.write(chunk, 0, chunk.size, AudioTrack.WRITE_BLOCKING)
                }
                1
            }
        } finally {
            try { track?.stop() } catch (_: Exception) {}
            track?.release()
        }

        if (cancel.get()) return SynthAudio(FloatArray(0), sr)
        val all = FloatArray(received)
        var offset = 0
        for (chunk in chunks) {
            chunk.copyInto(all, offset)
            offset += chunk.size
        }
        return SynthAudio(all, sr)
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
