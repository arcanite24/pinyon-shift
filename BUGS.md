- [x] On native render, the main screen is completely green (fixed fa5079d)
  - Not native: byte-identical with native off. Caused by
    `--pinyon_shift_skip_opening_movies=true`: the skip hook
    (`PinyonShiftCompleteOpeningMovie`, 0x82E5D8AC) ends *every* XMedia movie,
    including the title loop `media/ui/videos/PressStart.wmv`, so its YUV
    planes stay zero (RGB 0,77,0). With movies playing the title is correct.
    Fix idea: only skip `media/ui/videos/splash_intros/*.wmv`.
- [x] Native render not working, defaulting to Xenos (obsolete)
  - The Xenos renderer and the renderer choice were removed (`e5dc399`,
    `83e5312`); the native executor is the only renderer. The old opt-in
    flags and the SNR03 vegetation fallback no longer exist. The route
    matrix (`fh1-fmv`, `fh1-opening-sync`, `fh1-rewind-sync`,
    `fh1-race-sync`, `fh1-modes-sync`, `fh1-buy-car`) passes natively with
    zero pack misses and zero executor skips.
- [x] (fixed fa5079d) When going back to title screen on native render, the "Single Player" select screen is completely corrupted in texture super pink noisy
  - Same root cause as the green title (movie skip): stale data in the
    PressStart.wmv planes. Identical in compat-only runs; clean with movies on.
- [ ] Car selection on an event has either pink correupted textures or mangled car textures/models
  - Not a texture decode bug. The cards are the profile's
    `Thumbnails/Thumbnail_N.xdc` files, which the game renders, resolves and
    compresses from guest memory when it saves a car. Builds before SDK
    `0bf0658` never copied that resolve back into guest memory, so the files
    hold stale memory: the stripes (XR-04 in
    docs/native-renderer/XENOS_RETIREMENT_BACKLOG.md). New cards are correct
    (about 34 KB each); cards saved by older builds stay striped (275-845 KB
    of compressed noise) until the game saves them again. Repairing those is
    NP-0.6 in docs/NATIVE_PORT_BACKLOG.md.

- [ ] Green and pink artifacts on race central. Happened only on blue band collect cinematic
- [ ] Buy a new car pre-race, has unlocked animation speed
- [x] Rally stage-two finish screen shows the underside of the terrain on Vulkan.
  - Reproduced with the stock owned Escort and normal F6 entry in
    `fh1-rally-full-garage-stage-finish.fh1test`, using the render-test-only
    native AI driver. The car's position stays stable between the results
    captures. The authored finish target is 12.51 metres below native terrain
    collision at the same X/Z. Rally preparation recipe 7 enables the existing
    native ground snap for referenced finish targets in the generated cache.
    Both results captures now show the correct road and terrain on Vulkan;
    native finish and checkpoint saving still pass. Other finish views and
    manual full-stage driving remain unqualified; see docs/DLC_BACKLOG.md.
