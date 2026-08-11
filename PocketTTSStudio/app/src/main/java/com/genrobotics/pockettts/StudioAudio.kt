package com.genrobotics.pockettts

import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.tanh

object StudioAudio {
    data class Mastering(
        val dcRemove: Boolean = true,
        val trimSilence: Boolean = true,
        val normalize: Boolean = true,
        val limiter: Boolean = true,
        val targetPeakDb: Float = -1.0f,
        val outputGainDb: Float = 0.0f,
        val fadeMs: Int = 8
    )

    fun process(input: SynthAudio, settings: Mastering): SynthAudio {
        if (input.samples.isEmpty()) return input
        var data = input.samples.copyOf()
        if (settings.dcRemove) data = removeDc(data)
        if (settings.trimSilence) data = trim(data, input.sampleRate)
        if (data.isEmpty()) return SynthAudio(data, input.sampleRate)

        if (settings.normalize) {
            val peak = peak(data)
            if (peak > 1e-7f) {
                val target = 10.0.pow(settings.targetPeakDb.toDouble() / 20.0).toFloat()
                val factor = target / peak
                for (i in data.indices) data[i] *= factor
            }
        }

        if (settings.outputGainDb != 0f) {
            val gain = 10.0.pow(settings.outputGainDb.toDouble() / 20.0).toFloat()
            for (i in data.indices) data[i] *= gain
        }

        if (settings.limiter) {
            // Smooth saturation above the mastering knee. This protects WAV export from
            // hard digital clipping while preserving low-level material linearly.
            val knee = 0.92f
            val span = 1f - knee
            for (i in data.indices) {
                val x = data[i]
                val a = abs(x)
                if (a > knee) {
                    val excess = (a - knee) / span
                    val limited = knee + span * tanh(excess.toDouble()).toFloat()
                    data[i] = if (x < 0f) -limited else limited
                }
                data[i] = data[i].coerceIn(-0.999f, 0.999f)
            }
        }

        applyFade(data, input.sampleRate, settings.fadeMs)
        return SynthAudio(data, input.sampleRate)
    }

    fun peak(samples: FloatArray): Float {
        var p = 0f
        for (s in samples) p = max(p, abs(s))
        return p
    }

    fun peakDb(samples: FloatArray): Double {
        val p = peak(samples).coerceAtLeast(1e-9f)
        return 20.0 * log10(p.toDouble())
    }

    fun rmsDb(samples: FloatArray): Double {
        if (samples.isEmpty()) return -120.0
        var sum = 0.0
        for (s in samples) sum += s.toDouble() * s.toDouble()
        val rms = kotlin.math.sqrt(sum / samples.size).coerceAtLeast(1e-9)
        return 20.0 * log10(rms)
    }

    private fun removeDc(samples: FloatArray): FloatArray {
        var mean = 0.0
        for (s in samples) mean += s
        mean /= samples.size
        val out = FloatArray(samples.size)
        for (i in samples.indices) out[i] = (samples[i] - mean.toFloat())
        return out
    }

    private fun trim(samples: FloatArray, sampleRate: Int): FloatArray {
        val threshold = 0.0032f // about -50 dBFS
        var first = 0
        while (first < samples.size && abs(samples[first]) < threshold) first++
        if (first >= samples.size) return FloatArray(0)
        var last = samples.lastIndex
        while (last > first && abs(samples[last]) < threshold) last--

        val pad = (sampleRate * 0.035).toInt()
        first = (first - pad).coerceAtLeast(0)
        last = (last + pad).coerceAtMost(samples.lastIndex)
        return samples.copyOfRange(first, last + 1)
    }

    private fun applyFade(samples: FloatArray, sampleRate: Int, fadeMs: Int) {
        if (fadeMs <= 0 || samples.isEmpty()) return
        val n = ((sampleRate * fadeMs) / 1000).coerceIn(1, samples.size / 2)
        for (i in 0 until n) {
            val g = i.toFloat() / n.toFloat()
            samples[i] *= g
            samples[samples.lastIndex - i] *= g
        }
    }
}
