package com.nekospeak.tts.engine

import android.content.Context
import com.nekospeak.tts.data.PrefsManager
import com.nekospeak.tts.engine.piper.PiperEngine
import com.nekospeak.tts.engine.pocket.PocketTtsEngine

object EngineFactory {
    fun createEngine(context: Context, modelId: String? = null): TtsEngine {
        val prefs = PrefsManager(context)
        val selectedModel = modelId ?: prefs.currentModel
        android.util.Log.i("EngineFactory", "Creating engine for $selectedModel")
        return when {
            selectedModel == "pocket_v1" -> PocketTtsEngine(context)
            selectedModel == "mms_malayalam" -> MalayalamMmsEngine(context)
            selectedModel == "kitten_nano" -> KokoroEngine(context)
            selectedModel.startsWith("piper") -> PiperEngine(context, selectedModel.removePrefix("piper_"))
            else -> KokoroEngine(context)
        }
    }
}
