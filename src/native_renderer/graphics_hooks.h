#pragma once

// Guest-code observers for FH1's frame boundary and title draw emitter,
// called from the mid-asm hooks in config/rexglue/analysis. They feed the
// critical-path trace and the source-frame counter. The GPU fence wait hook
// blocks the title's fence polling until the command processor writes.

namespace pinyon_shift::native_renderer {

// pinyon_shift_fh1_scene_size: resize the race's tiled scene in the title's
// tiling scenario table. Call before guest code runs: the renderer sizes its
// surfaces from the table when it starts.
void ApplySceneSize();

}  // namespace pinyon_shift::native_renderer
