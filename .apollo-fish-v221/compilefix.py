from pathlib import Path
import sys
p = Path(sys.argv[1]) / 'app/src/main/java/dev/heyapollo/mobile/PcmAudioPlayer.kt'
s = p.read_text()
old = 'val wrote = runCatching { audioTrack.write(bytes, offset, bytes.size - offset, AudioTrack.WRITE_BLOCKING) }.getOrElse { break }'
new = '''val wrote = try {\n                            audioTrack.write(bytes, offset, bytes.size - offset, AudioTrack.WRITE_BLOCKING)\n                        } catch (_: Throwable) {\n                            break\n                        }'''
if old not in s:
    raise SystemExit('Expected PcmAudioPlayer write line not found')
p.write_text(s.replace(old, new, 1))
