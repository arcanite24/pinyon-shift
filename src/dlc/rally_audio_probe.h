#pragma once

namespace rex { struct RuntimeConfig; }
namespace pinyon_shift::rally {
// Private render-test capture of eight seconds of native PCM before SDL output.
void ConfigureAudioProbe(rex::RuntimeConfig& config);
void BeginAudioProbeCapture();
void FlushAudioProbeCapture();
}
