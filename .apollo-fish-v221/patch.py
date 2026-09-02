from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'app/build.gradle.kts'
s=p.read_text()
s=s.replace('versionCode = 22','versionCode = 23').replace('versionName = "2.2.0"','versionName = "2.2.1"')
p.write_text(s)

p=root/'app/src/main/java/dev/heyapollo/mobile/RealtimeSpeechQueue.kt'
s=p.read_text()
old='''            if (cut < 18 && text.length < 80) break\n            val segment = text.substring(0, cut + 1).trim()\n'''
new='''            // Realtime rule: never hold a completed natural sentence just because it is short.\n            // The old <18/<80 guard made greetings such as "I'm good!" wait until generation ended.\n            if (cut < 5 && text.length < 40) break\n            val segment = text.substring(0, cut + 1).trim()\n'''
if old not in s: raise SystemExit('RealtimeSpeechQueue target not found')
p.write_text(s.replace(old,new,1))

p=root/'app/src/main/java/dev/heyapollo/mobile/PcmAudioPlayer.kt'
p.write_text(r'''package dev.heyapollo.mobile

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.max

/** True hard-cancel PCM player: STOP invalidates/drains queued audio synchronously. */
class PcmAudioPlayer(
    scope: CoroutineScope,
    private val onProgress: (sequence: Int, playedMilliseconds: Long) -> Unit,
) {
    private sealed interface Command {
        data class Prepare(val sampleRate: Int, val sequence: Int?, val generation: Long) : Command
        data class Data(val bytes: ByteArray, val generation: Long) : Command
        data class Stop(val generation: Long) : Command
        data object Release : Command
    }
    private val commandChannel = Channel<Command>(Channel.UNLIMITED)
    private val generation = AtomicLong(1L)
    private val activeTrack = AtomicReference<AudioTrack?>(null)
    private val worker: Job = scope.launch(Dispatchers.IO) { consume() }

    fun prepare(sampleRate: Int, sequence: Int?) {
        val g = generation.get()
        commandChannel.trySend(Command.Prepare(sampleRate, sequence, g))
    }
    fun enqueue(bytes: ByteArray) {
        if (bytes.isEmpty()) return
        val g = generation.get()
        commandChannel.trySend(Command.Data(bytes.copyOf(), g))
    }
    fun stop() {
        val nextGeneration = generation.incrementAndGet()
        hardReleaseTrack()
        while (commandChannel.tryReceive().isSuccess) Unit
        commandChannel.trySend(Command.Stop(nextGeneration))
    }
    fun release() {
        generation.incrementAndGet()
        hardReleaseTrack()
        while (commandChannel.tryReceive().isSuccess) Unit
        commandChannel.trySend(Command.Release)
    }
    private fun hardReleaseTrack() {
        val t = activeTrack.getAndSet(null) ?: return
        runCatching { t.pause() }
        runCatching { t.flush() }
        runCatching { t.stop() }
        runCatching { t.release() }
    }
    private suspend fun consume() {
        var sampleRate = ApolloProtocol.DEFAULT_TTS_SAMPLE_RATE
        var sequence: Int? = null
        var writtenBytes = 0L
        var lastAckAt = 0L
        var carry: Byte? = null

        fun ensureTrack(expectedGeneration: Long): AudioTrack? {
            if (expectedGeneration != generation.get()) return null
            activeTrack.get()?.let { return it }
            val minBuffer = AudioTrack.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val built = AudioTrack.Builder()
                .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(AudioFormat.Builder().setSampleRate(sampleRate).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setBufferSizeInBytes(max(minBuffer, sampleRate / 2))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
            if (expectedGeneration != generation.get()) {
                runCatching { built.release() }
                return null
            }
            activeTrack.set(built)
            built.play()
            return built
        }

        for (command in commandChannel) {
            when (command) {
                is Command.Prepare -> {
                    if (command.generation != generation.get()) continue
                    if (activeTrack.get() != null && sampleRate != command.sampleRate) hardReleaseTrack()
                    sampleRate = command.sampleRate.coerceAtLeast(8_000)
                    sequence = command.sequence
                    writtenBytes = 0L
                    lastAckAt = 0L
                    carry = null
                }
                is Command.Data -> {
                    if (command.generation != generation.get()) continue
                    var bytes = command.bytes
                    carry?.let { first -> bytes = byteArrayOf(first) + bytes; carry = null }
                    if (bytes.size % 2 != 0) { carry = bytes.last(); bytes = bytes.copyOf(bytes.size - 1) }
                    if (bytes.isEmpty()) continue
                    val audioTrack = ensureTrack(command.generation) ?: continue
                    var offset = 0
                    while (offset < bytes.size && command.generation == generation.get()) {
                        val wrote = runCatching { audioTrack.write(bytes, offset, bytes.size - offset, AudioTrack.WRITE_BLOCKING) }.getOrElse { break }
                        if (wrote <= 0) break
                        offset += wrote
                        writtenBytes += wrote
                        val playedMs = writtenBytes * 1000L / (sampleRate * 2L)
                        val currentSequence = sequence
                        if (currentSequence != null && playedMs - lastAckAt >= 1_000L) {
                            lastAckAt = playedMs
                            onProgress(currentSequence, playedMs)
                        }
                    }
                }
                is Command.Stop -> { hardReleaseTrack(); writtenBytes = 0L; lastAckAt = 0L; carry = null; sequence = null }
                Command.Release -> { hardReleaseTrack(); commandChannel.close(); break }
            }
        }
    }
}
''')

p=root/'README.md'
p.write_text(p.read_text()+'''\n\n## v2.2.1 hard-stop latency fix\n- Completed short clauses stream to Fish immediately.\n- PCM STOP invalidates and drains old audio synchronously, so queued speech cannot continue after interrupt.\n''')
