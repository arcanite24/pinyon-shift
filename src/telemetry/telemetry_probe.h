#pragma once

#include <string_view>
#include <vector>

namespace pinyon_shift::telemetry {

// A recording of candidate car fields beside the runtime log (telemetry_probe),
// to confirm what each one means against a drive before telemetry sends it.
// Two CSVs: a fast one (about 30 rows a second) of chosen fields, and a slow
// one (twice a second) of a whole block, for finding fields by correlation.
bool ProbeWanted();
// True when the next fast or slow row is due; the caller then reads and writes it.
bool ProbeFastDue();
bool ProbeSlowDue();
// `header` is written once per file; values follow it in the same order.
void ProbeWriteFast(std::string_view header, const std::vector<float>& values);
void ProbeWriteSlow(std::string_view header, const std::vector<float>& values);

}  // namespace pinyon_shift::telemetry
