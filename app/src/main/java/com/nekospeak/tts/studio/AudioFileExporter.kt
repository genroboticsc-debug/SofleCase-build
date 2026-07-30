package com.nekospeak.tts.studio

import android.content.ContentValues
import android.content.Context
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import java.io.File
import java.io.FileInputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

enum class StudioAudioFormat(val extension: String, val mimeType: String) {
    WAV("wav", "audio/wav"),
    AAC("m4a", "audio/mp4"),
    OPUS("ogg", "audio/ogg")
}

object AudioFileExporter {
    suspend fun export(
        context: Context,
        pcmFile: File,
        sampleRate: Int,
        format: StudioAudioFormat,
        bitrateKbps: Int,
        baseName: String
    ): Uri = withContext(Dispatchers.IO) {
        require(pcmFile.exists() && pcmFile.length() > 0L) { "Generated audio is empty" }
        when (format) {
            StudioAudioFormat.WAV -> exportWav(context, pcmFile, sampleRate, baseName)
            StudioAudioFormat.AAC -> exportCompressed(context, pcmFile, sampleRate, bitrateKbps, baseName, false)
            StudioAudioFormat.OPUS -> {
                if (Build.VERSION.SDK_INT < 29) {
                    exportCompressed(context, pcmFile, sampleRate, bitrateKbps, baseName, false)
                } else {
                    exportCompressed(context, pcmFile, sampleRate, bitrateKbps, baseName, true)
                }
            }
        }
    }

    private fun exportWav(context: Context, pcmFile: File, sampleRate: Int, baseName: String): Uri {
        val uri = createMediaUri(context, "$baseName.wav", "audio/wav")
        context.contentResolver.openOutputStream(uri, "w")!!.use { output ->
            writeWavHeader(output, pcmFile.length(), sampleRate)
            FileInputStream(pcmFile).use { it.copyTo(output, 256 * 1024) }
        }
        finishMediaUri(context, uri)
        return uri
    }

    private fun exportCompressed(
        context: Context,
        pcmFile: File,
        sampleRate: Int,
        bitrateKbps: Int,
        baseName: String,
        opus: Boolean
    ): Uri {
        val temp = File(context.cacheDir, "${baseName}_${System.nanoTime()}.${if (opus) "ogg" else "m4a"}")
        encodePcmToContainer(pcmFile, temp, sampleRate, bitrateKbps * 1000, opus)
        val name = "$baseName.${if (opus) "ogg" else "m4a"}"
        val mime = if (opus) "audio/ogg" else "audio/mp4"
        val uri = createMediaUri(context, name, mime)
        context.contentResolver.openOutputStream(uri, "w")!!.use { output ->
            FileInputStream(temp).use { it.copyTo(output, 256 * 1024) }
        }
        temp.delete()
        finishMediaUri(context, uri)
        return uri
    }

    private fun encodePcmToContainer(
        pcmFile: File,
        outputFile: File,
        sampleRate: Int,
        bitrate: Int,
        opus: Boolean
    ) {
        val mime = if (opus) MediaFormat.MIMETYPE_AUDIO_OPUS else MediaFormat.MIMETYPE_AUDIO_AAC
        val mediaFormat = MediaFormat.createAudioFormat(mime, sampleRate, 1).apply {
            setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 64 * 1024)
            if (!opus) setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
        }
        val codec = MediaCodec.createEncoderByType(mime)
        val muxerFormat = if (opus) MediaMuxer.OutputFormat.MUXER_OUTPUT_OGG else MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4
        val muxer = MediaMuxer(outputFile.absolutePath, muxerFormat)
        var muxerStarted = false
        var trackIndex = -1
        var totalSamples = 0L
        var inputEnded = false
        var outputEnded = false
        val bufferInfo = MediaCodec.BufferInfo()

        try {
            codec.configure(mediaFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            codec.start()
            FileInputStream(pcmFile).use { input ->
                while (!outputEnded) {
                    if (!inputEnded) {
                        val inputIndex = codec.dequeueInputBuffer(10_000)
                        if (inputIndex >= 0) {
                            val inputBuffer = codec.getInputBuffer(inputIndex)!!
                            inputBuffer.clear()
                            val maxRead = inputBuffer.remaining().let { it - (it % 2) }
                            val bytes = ByteArray(maxRead)
                            val count = input.read(bytes)
                            if (count < 0) {
                                val pts = totalSamples * 1_000_000L / sampleRate
                                codec.queueInputBuffer(inputIndex, 0, 0, pts, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                inputEnded = true
                            } else {
                                val evenCount = count - (count % 2)
                                inputBuffer.put(bytes, 0, evenCount)
                                val pts = totalSamples * 1_000_000L / sampleRate
                                codec.queueInputBuffer(inputIndex, 0, evenCount, pts, 0)
                                totalSamples += evenCount / 2L
                            }
                        }
                    }

                    when (val outputIndex = codec.dequeueOutputBuffer(bufferInfo, 10_000)) {
                        MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                        MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                            check(!muxerStarted) { "Encoder output format changed twice" }
                            trackIndex = muxer.addTrack(codec.outputFormat)
                            muxer.start()
                            muxerStarted = true
                        }
                        else -> if (outputIndex >= 0) {
                            val outputBuffer = codec.getOutputBuffer(outputIndex)!!
                            if (bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) {
                                bufferInfo.size = 0
                            }
                            if (bufferInfo.size > 0) {
                                check(muxerStarted) { "Muxer has not started" }
                                outputBuffer.position(bufferInfo.offset)
                                outputBuffer.limit(bufferInfo.offset + bufferInfo.size)
                                muxer.writeSampleData(trackIndex, outputBuffer, bufferInfo)
                            }
                            outputEnded = bufferInfo.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                            codec.releaseOutputBuffer(outputIndex, false)
                        }
                    }
                }
            }
        } finally {
            runCatching { codec.stop() }
            runCatching { codec.release() }
            if (muxerStarted) runCatching { muxer.stop() }
            runCatching { muxer.release() }
        }
    }

    private fun createMediaUri(context: Context, displayName: String, mimeType: String): Uri {
        val values = ContentValues().apply {
            put(MediaStore.Audio.Media.DISPLAY_NAME, displayName)
            put(MediaStore.Audio.Media.MIME_TYPE, mimeType)
            if (Build.VERSION.SDK_INT >= 29) {
                put(MediaStore.Audio.Media.RELATIVE_PATH, "Music/NekoSpeak Studio")
                put(MediaStore.Audio.Media.IS_PENDING, 1)
            }
        }
        return requireNotNull(context.contentResolver.insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values)) {
            "Unable to create output audio file"
        }
    }

    private fun finishMediaUri(context: Context, uri: Uri) {
        if (Build.VERSION.SDK_INT >= 29) {
            context.contentResolver.update(uri, ContentValues().apply {
                put(MediaStore.Audio.Media.IS_PENDING, 0)
            }, null, null)
        }
    }

    private fun writeWavHeader(output: OutputStream, pcmBytes: Long, sampleRate: Int) {
        val byteRate = sampleRate * 2
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        header.put("RIFF".toByteArray(Charsets.US_ASCII))
        header.putInt((36L + pcmBytes).coerceAtMost(Int.MAX_VALUE.toLong()).toInt())
        header.put("WAVE".toByteArray(Charsets.US_ASCII))
        header.put("fmt ".toByteArray(Charsets.US_ASCII))
        header.putInt(16)
        header.putShort(1.toShort())
        header.putShort(1.toShort())
        header.putInt(sampleRate)
        header.putInt(byteRate)
        header.putShort(2.toShort())
        header.putShort(16.toShort())
        header.put("data".toByteArray(Charsets.US_ASCII))
        header.putInt(pcmBytes.coerceAtMost(Int.MAX_VALUE.toLong()).toInt())
        output.write(header.array())
    }
}
