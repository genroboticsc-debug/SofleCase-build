# Pocket TTS Ultra Studio Android

Native ARM64 Android engineering build of Pocket TTS using sherpa-onnx 1.13.5.

## Implemented in 0.1.0

- Local PocketTTS INT8 inference
- Zero-shot voice cloning from WAV
- Runtime model download and integrity-by-manifest validation
- Streaming playback with cancellation
- Speed, temperature, sampling-step, seed, silence and CPU-thread controls
- Waveform preview, replay and WAV export
- Dark Jetpack Compose studio UI
- ARM64-only APK for modern Android phones such as Redmi Note 12

## Model

The APK does not embed the ~203 MB model. Open the MODEL tab after installation and download it once. Synthesis is offline after installation.

## Licensing

The current sherpa-onnx PocketTTS INT8 model card marks the model non-commercial. Review the model and upstream project licenses before commercial redistribution or use.
