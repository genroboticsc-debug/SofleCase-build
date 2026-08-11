package com.genrobotics.pockettts

import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import kotlin.math.roundToInt

enum class EngineKind { POCKET, PIPER }

data class ModelPack(
    val id: String,
    val displayName: String,
    val engine: EngineKind,
    val languageCode: String,
    val languageName: String,
    val nativeLanguageName: String,
    val voiceName: String,
    val archiveUrl: String,
    val dirName: String,
    val modelFile: String = "",
    val sampleRateHint: Int,
    val speakers: Int = 1,
    val cloneVoice: Boolean = false,
    val quality: String = "Medium",
    val sampleText: String,
    val description: String
)

object ModelCatalog {
    val packs = listOf(
        ModelPack(
            id = "pocket_en",
            displayName = "Kyutai PocketTTS • English",
            engine = EngineKind.POCKET,
            languageCode = "en",
            languageName = "English",
            nativeLanguageName = "English",
            voiceName = "Clone / Reference",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-pocket-tts-int8-2026-01-26.tar.bz2",
            dirName = "sherpa-onnx-pocket-tts-int8-2026-01-26",
            sampleRateHint = 24000,
            cloneVoice = true,
            quality = "Zero-shot clone",
            sampleText = "Pocket TTS Ultra Studio is generating this speech completely on this Android phone.",
            description = "Kyutai PocketTTS via sherpa-onnx. Streaming CPU inference with zero-shot reference-WAV voice cloning."
        ),
        ModelPack(
            id = "ml_meera",
            displayName = "Malayalam • Meera",
            engine = EngineKind.PIPER,
            languageCode = "ml",
            languageName = "Malayalam",
            nativeLanguageName = "മലയാളം",
            voiceName = "Meera",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-ml_IN-meera-medium.tar.bz2",
            dirName = "vits-piper-ml_IN-meera-medium",
            modelFile = "ml_IN-meera-medium.onnx",
            sampleRateHint = 22050,
            quality = "Medium • Female",
            sampleText = "നമസ്കാരം. ഇത് പൂർണ്ണമായും ഫോണിൽ പ്രവർത്തിക്കുന്ന മലയാളം ശബ്ദ സിന്തസിസ് സ്റ്റുഡിയോ ആണ്.",
            description = "Malayalam Meera local neural voice. Piper/VITS model running through the same sherpa-onnx Android runtime."
        ),
        ModelPack(
            id = "ml_arjun",
            displayName = "Malayalam • Arjun",
            engine = EngineKind.PIPER,
            languageCode = "ml",
            languageName = "Malayalam",
            nativeLanguageName = "മലയാളം",
            voiceName = "Arjun",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-ml_IN-arjun-medium.tar.bz2",
            dirName = "vits-piper-ml_IN-arjun-medium",
            modelFile = "ml_IN-arjun-medium.onnx",
            sampleRateHint = 22050,
            quality = "Medium • Male",
            sampleText = "മണ്ണ് മരിക്കുമ്പോൾ കാട്ടിലെ വെള്ളവും മരിക്കുന്നു. ശബ്ദം പൂർണ്ണമായും ഈ ഫോണിൽ തന്നെ സൃഷ്ടിക്കുന്നു.",
            description = "Malayalam Arjun local neural voice. Piper/VITS model running through sherpa-onnx."
        ),
        ModelPack(
            id = "fr_tom",
            displayName = "French • Tom",
            engine = EngineKind.PIPER,
            languageCode = "fr",
            languageName = "French",
            nativeLanguageName = "Français",
            voiceName = "Tom",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-fr_FR-tom-medium.tar.bz2",
            dirName = "vits-piper-fr_FR-tom-medium",
            modelFile = "fr_FR-tom-medium.onnx",
            sampleRateHint = 44100,
            quality = "Medium",
            sampleText = "Bonjour. Cette voix est générée entièrement hors ligne sur votre téléphone.",
            description = "French local neural voice pack for fully offline multilingual production."
        ),
        ModelPack(
            id = "de_thorsten",
            displayName = "German • Thorsten",
            engine = EngineKind.PIPER,
            languageCode = "de",
            languageName = "German",
            nativeLanguageName = "Deutsch",
            voiceName = "Thorsten",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-de_DE-thorsten-medium.tar.bz2",
            dirName = "vits-piper-de_DE-thorsten-medium",
            modelFile = "de_DE-thorsten-medium.onnx",
            sampleRateHint = 22050,
            quality = "Medium",
            sampleText = "Hallo. Diese Stimme wird vollständig offline auf diesem Telefon erzeugt.",
            description = "German Thorsten medium local neural voice pack."
        ),
        ModelPack(
            id = "es_sharvard",
            displayName = "Spanish • Sharvard",
            engine = EngineKind.PIPER,
            languageCode = "es",
            languageName = "Spanish",
            nativeLanguageName = "Español",
            voiceName = "Sharvard",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-es_ES-sharvard-medium.tar.bz2",
            dirName = "vits-piper-es_ES-sharvard-medium",
            modelFile = "es_ES-sharvard-medium.onnx",
            sampleRateHint = 22050,
            speakers = 2,
            quality = "Medium • 2 speakers",
            sampleText = "Hola. Esta voz se genera completamente sin conexión en este teléfono.",
            description = "Spanish Sharvard local neural pack with two speaker IDs."
        ),
        ModelPack(
            id = "it_paola",
            displayName = "Italian • Paola",
            engine = EngineKind.PIPER,
            languageCode = "it",
            languageName = "Italian",
            nativeLanguageName = "Italiano",
            voiceName = "Paola",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-it_IT-paola-medium.tar.bz2",
            dirName = "vits-piper-it_IT-paola-medium",
            modelFile = "it_IT-paola-medium.onnx",
            sampleRateHint = 22050,
            quality = "Medium",
            sampleText = "Ciao. Questa voce viene generata completamente offline sul telefono.",
            description = "Italian Paola medium local neural voice pack."
        ),
        ModelPack(
            id = "pt_faber",
            displayName = "Portuguese • Faber",
            engine = EngineKind.PIPER,
            languageCode = "pt",
            languageName = "Portuguese",
            nativeLanguageName = "Português",
            voiceName = "Faber",
            archiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-pt_BR-faber-medium.tar.bz2",
            dirName = "vits-piper-pt_BR-faber-medium",
            modelFile = "pt_BR-faber-medium.onnx",
            sampleRateHint = 22050,
            quality = "Medium",
            sampleText = "Olá. Esta voz é gerada totalmente offline neste telefone.",
            description = "Brazilian Portuguese Faber medium local neural voice pack."
        )
    )

    fun byId(id: String): ModelPack = packs.firstOrNull { it.id == id } ?: packs.first()
    fun languagePacks(code: String): List<ModelPack> = packs.filter { it.languageCode == code }
    val languages: List<String> = packs.map { it.languageCode }.distinct()
}

data class SynthAudio(val samples: FloatArray, val sampleRate: Int) {
    val durationSeconds: Double get() = if (sampleRate > 0) samples.size.toDouble() / sampleRate else 0.0

    fun save(fileName: String): Boolean = try {
        val file = File(fileName)
        file.parentFile?.mkdirs()
        val dataBytes = samples.size * 2
        BufferedOutputStream(FileOutputStream(file), 128 * 1024).use { out ->
            fun le16(v: Int) {
                out.write(v and 0xff)
                out.write((v ushr 8) and 0xff)
            }
            fun le32(v: Int) {
                out.write(v and 0xff)
                out.write((v ushr 8) and 0xff)
                out.write((v ushr 16) and 0xff)
                out.write((v ushr 24) and 0xff)
            }
            out.write("RIFF".toByteArray(Charsets.US_ASCII))
            le32(36 + dataBytes)
            out.write("WAVE".toByteArray(Charsets.US_ASCII))
            out.write("fmt ".toByteArray(Charsets.US_ASCII))
            le32(16)
            le16(1)
            le16(1)
            le32(sampleRate)
            le32(sampleRate * 2)
            le16(2)
            le16(16)
            out.write("data".toByteArray(Charsets.US_ASCII))
            le32(dataBytes)
            for (sample in samples) {
                val pcm = (sample.coerceIn(-1f, 1f) * 32767f).roundToInt()
                le16(pcm)
            }
        }
        true
    } catch (_: Throwable) {
        false
    }
}

data class RenderTake(
    val file: File,
    val packId: String,
    val title: String,
    val createdAt: Long,
    val durationSeconds: Double,
    val sampleRate: Int,
    val rtf: Double,
    val peakDb: Double
)
