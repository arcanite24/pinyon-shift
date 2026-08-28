import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererContractTests(unittest.TestCase):
    def test_census_storage_is_reset_without_large_stack_temporaries(self) -> None:
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("g_draw_census = {};", source)
        self.assertNotIn("g_dependency_census = {};", source)
        self.assertIn(
            "std::memset(&g_draw_census, 0, sizeof(g_draw_census));", source
        )
        self.assertIn(
            "std::memset(&g_dependency_census, 0, sizeof(g_dependency_census));",
            source,
        )

    def test_graphics_hook_has_one_pass_through_owner(self):
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(analysis.count('name = "PinyonShiftObserveGraphicsFrame"'), 1)
        hook = analysis.split('name = "PinyonShiftObserveGraphicsFrame"', 1)[0]
        hook = hook.rsplit("[[midasm_hook]]", 1)[1]
        self.assertIn("address = 0x829EFEB8", hook)
        self.assertNotIn("jump_address", hook)
        self.assertNotIn("after_instruction", hook)
        self.assertNotIn("registers", hook)

    def test_census_is_default_off_and_bounded(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("pinyon_shift_native_renderer_census, false", source)
        self.assertIn("kFrameSummaryInterval = 300", source)
        self.assertIn("kSignatureCapacity = 4096", source)
        self.assertIn("kSummaryLimit = 16", source)
        self.assertIn("kResolveTargetCapacity = 4096", source)
        self.assertIn("kResolvePageCapacity = 32768", source)
        self.assertIn("kResolveSummaryLimit = 32", source)
        self.assertIn("unique_signature_count", source)
        self.assertIn("overflow_draw_count", source)
        self.assertIn("kRequiresRestart", source)
        self.assertIn('"mode", "pass_through"', source)
        self.assertNotIn("REX_STORE", source)
        self.assertNotIn("GuestPtr", source)

    def test_scene_markers_and_classifier_are_explicit_and_safe(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        classifier = (
            ROOT / "config/native-renderer/pass-classifier.json"
        ).read_text(encoding="utf-8")
        summarizer = (
            ROOT / "tools/summarize-native-renderer-census.py"
        ).read_text(encoding="utf-8")

        self.assertIn("native_renderer.census.scene_marker", source)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_SCENE", source)
        self.assertIn("[ValidateSet('unmarked', 'front_end', 'garage'", capture)
        self.assertIn('"maximum_drift_records": 32', classifier)
        self.assertIn('"confidence": "medium"', classifier)
        self.assertIn('"retained_unknown"', summarizer)
        self.assertIn('"retained_on_xenos"', summarizer)

    def test_resolve_dependency_observer_is_passive_and_payload_free(self):
        patch = (
            ROOT
            / "patches/rexglue/0045-graphics-resolve-dependency-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("GraphicsCopyObservation", patch)
        self.assertIn("GraphicsCopyObserver", patch)
        self.assertIn("texture_fetch_addresses", patch)
        self.assertIn("texture_fetch_mip_addresses", patch)
        self.assertIn("copy_observer(observation);", patch)
        self.assertLess(
            patch.index("copy_succeeded = render_target_cache_->Resolve"),
            patch.index("copy_observer(observation);"),
        )
        for forbidden in (
            "shader_code",
            "texture_data",
            "render_target_data",
            "vertex_data",
            "payload",
            "suppress",
        ):
            self.assertNotIn(forbidden, patch)

        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('"native_renderer.census.resolve_dependency"', source)
        self.assertIn('"unknown_uninstrumented"', source)
        self.assertIn('{"suppression_eligible", "false"}', source)
        self.assertIn("page_count > bounded_page_count", source)
        self.assertNotIn("REX_STORE", source)

    def test_dependency_ledger_keeps_gate_b_closed(self):
        ledger = (
            ROOT / "docs/native-renderer/GUEST_VISIBLE_RENDER_DEPENDENCIES.md"
        ).read_text(encoding="utf-8")
        self.assertIn("No render target is suppression-eligible yet.", ledger)
        self.assertIn("Gate B remains closed", ledger)
        self.assertIn("unknown_uninstrumented", ledger)
        self.assertIn("unknown_unclassified", ledger)
        self.assertIn("capture-native-renderer-census.ps1", ledger)
        self.assertIn("summarize-native-renderer-census.py", ledger)

    def test_draw_observer_is_read_only_and_contains_no_payload(self):
        patch = (ROOT / "patches/rexglue/0044-graphics-draw-observer.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("GraphicsDrawObservation", patch)
        self.assertIn("auto draw_observer = graphics_system_->draw_observer();", patch)
        self.assertIn("if (draw_observer) {", patch)
        self.assertIn("draw_observer(observation);", patch)
        self.assertLess(
            patch.index("draw_observer(observation);"),
            patch.index("draw_succeeded = IssueDraw"),
        )
        self.assertLess(
            patch.index("if (draw_observer) {"),
            patch.index("GraphicsDrawObservation observation;"),
        )
        self.assertIn("vertex_shader_hash", patch)
        self.assertIn("pixel_shader_hash", patch)
        self.assertIn("vertex_memexport", patch)
        for forbidden in ("shader_code", "texture_data", "vertex_data", "payload"):
            self.assertNotIn(forbidden, patch)

        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        signature = source.split("DrawSignature(", 1)[1].split(
            "CandidateSignature", 1
        )[0]
        self.assertIn("observation.primitive_type", signature)
        self.assertIn("observation.source_select", signature)
        self.assertNotIn("observation.initiator", signature)
        self.assertNotIn("observation.rb_blendcontrol", signature)
        self.assertNotIn("samples_resolved_target", signature)

    def test_census_has_no_native_renderer_or_suppression_api(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        forbidden = (
            "native_rhi",
            "NativeRHI",
            "IssueDraw",
            "IssueCopy",
            "SetDrawSuppression",
            "SetCopySuppression",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("src/native_renderer/graphics_hooks.cpp"), 2)

    def test_native_guest_output_registration_is_inert_and_backend_neutral(self):
        patch = (
            ROOT
            / "patches/rexglue/0046-native-guest-output-callback-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("NativeGuestOutputRenderContext", patch)
        self.assertIn("NativeGuestOutputBackend", patch)
        self.assertIn("NativeGuestOutputRendererRegistration", patch)
        self.assertIn("return renderer ? renderer(context) : false;", patch)
        self.assertIn("defaults to inert yield", patch)
        self.assertIn("preserves callback result", patch)
        for forbidden in ("IssueSwap", "ResourceBarrier", "ClearRenderTargetView"):
            self.assertNotIn(forbidden, patch)

    def test_d3d12_guest_output_callback_preserves_state_and_fallback(self):
        patch = (
            ROOT / "patches/rexglue/0047-d3d12-native-guest-output-context.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("NativeGuestOutputClearColor", patch)
        self.assertIn("D3DClearUnorderedAccessViewFloat", patch)
        self.assertIn("kGuestOutputInternalState", patch)
        self.assertIn("native_guest_output_renderer().Get()", patch)
        self.assertIn("native_context.backend", patch)
        self.assertNotIn("SetDrawSuppression", patch)

        source = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("pinyon_shift_native_renderer_diagnostic_clear, false", source)
        self.assertIn("g_failure_latched", source)
        self.assertIn('{"fallback", "xenos"}', source)
        self.assertIn("context.clear_color(context, color)", source)

    def test_diagnostic_triangle_and_recovery_remain_backend_owned(self):
        patch = (
            ROOT / "patches/rexglue/0049-native-guest-output-diagnostic-triangle.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("NativeGuestOutputDrawDiagnosticTriangle", patch)
        self.assertIn("native_guest_output_triangle_cs", patch)
        self.assertIn("D3DSetComputeRootDescriptorTable", patch)
        self.assertIn("kGuestOutputInternalState", patch)
        self.assertNotIn("SetDrawSuppression", patch)

        source = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn('pinyon_shift_native_renderer, "xenos"', source)
        self.assertIn('mode == "diagnostic_triangle"', source)
        self.assertIn("context.draw_diagnostic_triangle", source)
        self.assertIn('"unsupported_mode"', source)

        settings = (ROOT / "tools/set-graphics-experiment.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'ResetRenderer'", settings)
        self.assertIn("pinyon_shift_native_renderer", settings)

        report = (ROOT / "tools/create-crash-report.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("claimed_frames", report)
        self.assertIn("failure_reason", report)

    def test_shader_capture_is_local_bounded_and_passive(self):
        patch = (
            ROOT
            / "patches/rexglue/0050-d3d12-shader-translation-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("GraphicsShaderTranslationObservation", patch)
        self.assertIn("translation.translated_binary().data()", patch)
        self.assertIn("translation.modification()", patch)
        self.assertIn("if (!translation.is_valid())", patch)
        self.assertNotIn("SetDrawSuppression", patch)
        self.assertNotIn("SetCopySuppression", patch)

        source = (
            ROOT / "src/native_renderer/shader_capture.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR", source)
        self.assertIn("kMaximumEntries = 256", source)
        self.assertIn("kMaximumBytecodeBytes = 16 * 1024 * 1024", source)
        self.assertIn("kMaximumCaptureBytes = 128 * 1024 * 1024", source)
        self.assertIn('component.native() == L".local"', source)
        self.assertIn('std::memcmp(bytecode.data(), "DXBC", 4)', source)
        self.assertIn("pinyon-shift.native-shader-pack.v1", source)
        self.assertIn('{"fallback", "xenos"}', source)
        self.assertNotIn("guest_hash", source.split(
            'diagnostics::RecordEvent("native_renderer.shader_capture.installed"', 1
        )[1])

        launcher = (ROOT / "tools/launch-preview.ps1").read_text(
            encoding="utf-8"
        )
        capture = (
            ROOT / "tools/capture-native-renderer-shaders.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR", launcher)
        self.assertIn("-StateRoot $resolvedStateRoot", capture)
        self.assertIn("ForzaProfile", capture)
        self.assertIn("repository .local directory", capture)

    def test_candidate_state_is_bounded_metadata_before_draw(self):
        patch = (
            ROOT / "patches/rexglue/0051-graphics-draw-candidate-state.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("kGraphicsVertexBindingObservationLimit = 8", patch)
        self.assertIn("index_format", patch)
        self.assertIn("index_endianness", patch)
        self.assertIn("vertex_binding_overflow", patch)
        self.assertIn("rb_blendcontrol", patch)
        self.assertIn("rb_depthcontrol", patch)
        self.assertIn("pa_su_sc_mode_cntl", patch)
        for forbidden in (
            "vertex_data",
            "index_data",
            "texture_data",
            "constant_data",
            "SetDrawSuppression",
        ):
            self.assertNotIn(forbidden, patch)

        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('"suppression_allowed": False', (
            ROOT / "tools/select-native-renderer-candidate.py"
        ).read_text(encoding="utf-8"))
        self.assertIn("IsOpaqueColorState", source)
        self.assertIn("samples_resolved_target", source)
        reset_window = source.split("void ResetDrawCensus()", 1)[1].split(
            "void ResetPreparedShaderPairs()", 1
        )[0]
        self.assertNotIn("g_prepared_shader_pairs", reset_window)
        self.assertIn("ResetPreparedShaderPairs();", source)

        app = (ROOT / "src/pinyon_shift_app.cpp").read_text(encoding="utf-8")
        close_path = app.split("bool PinyonShiftApp::OnWindowCloseRequested()", 1)[
            1
        ].split("void PinyonShiftApp::OnShutdown()", 1)[0]
        self.assertIn("UninstallGraphicsCensus", close_path)

        prepared_patch = (
            ROOT / "patches/rexglue/0052-d3d12-prepared-draw-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("GraphicsPreparedDrawObservation", prepared_patch)
        self.assertIn("vertex_specialization_mask", prepared_patch)
        self.assertIn("pixel_specialization_mask", prepared_patch)
        self.assertLess(
            prepared_patch.index("GetD3D12PipelineByHandle"),
            prepared_patch.index("prepared_draw_observer(observation);"),
        )
        self.assertLess(
            prepared_patch.index("prepared_draw_observer(observation);"),
            prepared_patch.index("// Update the textures"),
        )
        self.assertNotIn("SetDrawSuppression", prepared_patch)
        self.assertIn("g_pending_candidate.sample = observation;", source)
        self.assertIn(
            "sample.vertex_shader_hash = observation.vertex_shader_hash;",
            source,
        )
        self.assertIn(
            'fmt::format("{:016X}", entry.vertex_specialization_mask)',
            source,
        )
        self.assertIn("candidate_prepared_without_observation", source)

        declaration_patch = (
            ROOT / "patches/rexglue/0053-graphics-vertex-declaration-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("kGraphicsVertexAttributeObservationLimit = 32", declaration_patch)
        self.assertIn("VGT_INDX_OFFSET", declaration_patch)
        self.assertIn("VGT_MIN_VTX_INDX", declaration_patch)
        self.assertIn("VGT_MAX_VTX_INDX", declaration_patch)
        self.assertIn("fetch_word_mask", declaration_patch)
        self.assertIn("vertex_attribute_overflow", declaration_patch)
        for forbidden in (
            "vertex_data",
            "index_data",
            "TranslatePhysical",
            "SetDrawSuppression",
            "IssueDraw",
        ):
            self.assertNotIn(forbidden, declaration_patch)

        draw_state_patch = (
            ROOT / "patches/rexglue/0054-graphics-draw-state-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("kGraphicsFloatConstantObservationLimit = 64", draw_state_patch)
        self.assertIn("constant_register_map", draw_state_patch)
        self.assertIn("XE_GPU_REG_SHADER_CONSTANT_256_X", draw_state_patch)
        self.assertIn("kGraphicsTextureFetchObservationLimit = 16", draw_state_patch)
        self.assertIn("instruction.attributes.mag_filter", draw_state_patch)
        self.assertIn("texture_state_overflow", draw_state_patch)
        for forbidden in (
            "TranslatePhysical",
            "SetDrawSuppression",
            "native_guest_output",
        ):
            self.assertNotIn(forbidden, draw_state_patch)

        index_reset_patch = (
            ROOT / "patches/rexglue/0055-graphics-index-reset-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("index_reset", index_reset_patch)
        self.assertIn("multi_prim_ib_ena", index_reset_patch)
        self.assertNotIn("TranslatePhysical", index_reset_patch)

        texture_layout_patch = (
            ROOT / "patches/rexglue/0056-graphics-texture-layout-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("TextureInfo::Prepare", texture_layout_patch)
        self.assertIn("FetchConstantType::kTexture", texture_layout_patch)
        self.assertIn("texture_fetch_base_lengths", texture_layout_patch)
        self.assertIn("texture_fetch_layout_valid_mask", texture_layout_patch)
        self.assertNotIn("TranslatePhysical", texture_layout_patch)

        prepared_pipeline_patch = (
            ROOT / "patches/rexglue/0057-d3d12-prepared-pipeline-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("normalized_depth_control", prepared_pipeline_patch)
        self.assertIn("bound_render_target_formats", prepared_pipeline_patch)
        self.assertIn("host_vertex_shader_type", prepared_pipeline_patch)
        self.assertNotIn("TranslatePhysical", prepared_pipeline_patch)
        self.assertNotIn("SetDrawSuppression", prepared_pipeline_patch)

        planner = (
            ROOT / "tools/build-native-geometry-contract.py"
        ).read_text(encoding="utf-8")
        self.assertIn("PHYSICAL_MASK = 0x1FFFFFFF", planner)
        self.assertIn('"guest_payload_scope"', planner)
        self.assertIn('"bounded_index_only"', planner)
        self.assertIn('"native_upload": False', planner)
        self.assertIn('"native_draw": False', planner)
        self.assertIn('"suppression_allowed": False', planner)
        self.assertIn('"xenos_authority": True', planner)

        scanner = (
            ROOT / "src/native_renderer/graphics_hooks.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE", scanner)
        self.assertIn("kMaximumIndexScanCount", scanner)
        self.assertIn("kMaximumIndexScanBytes", scanner)
        self.assertIn('"bounded_index_only"', scanner)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE", scanner)
        self.assertIn("kMaximumTextureScanTotalBytes", scanner)
        self.assertIn('"bounded_texture_only"', scanner)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE", scanner)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR", scanner)
        self.assertIn("kMaximumVertexSnapshotBytes", scanner)
        self.assertIn('"bounded_snapshot_only"', scanner)
        self.assertIn('"native_upload", "false"', scanner)
        self.assertIn('"native_draw", "false"', scanner)
        self.assertIn('"suppression_eligible", "false"', scanner)
        self.assertNotIn("SetDrawSuppression", scanner)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE", scanner)
        self.assertIn('"native_renderer.census.pass_follower"', scanner)
        self.assertIn("sample.draw_sequence == g_pass_follower.anchor_draw + 1", scanner)

        census_capture = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("PassAnchorSignature", census_capture)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE", census_capture)

        follower_selector = (
            ROOT / "tools/select-native-renderer-pass-follower.py"
        ).read_text(encoding="utf-8")
        self.assertIn("pinyon-shift.native-renderer-pass-follower.v1", follower_selector)
        self.assertIn('"suppression_allowed": False', follower_selector)
        self.assertIn('"xenos_authority": True', follower_selector)

        isolated_replay_patch = (
            ROOT / "patches/rexglue/0058-d3d12-isolated-draw-replay.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("GraphicsIsolatedDrawRequest", isolated_replay_patch)
        self.assertIn("BeginIsolatedReplayTarget", isolated_replay_patch)
        self.assertIn("EndIsolatedReplayTarget", isolated_replay_patch)
        self.assertIn("D3DDrawIndexedInstanced", isolated_replay_patch)
        self.assertIn("isolated_draw_request.completion", isolated_replay_patch)
        self.assertNotIn("SetDrawSuppression", isolated_replay_patch)
        isolated_draw_position = isolated_replay_patch.index(
            "if (isolated_draw_request.requested)"
        )
        guest_draw_position = isolated_replay_patch.index(
            "PROFILE_DRAW_CALL();", isolated_draw_position
        )
        self.assertLess(isolated_draw_position, guest_draw_position)

        isolated_readback_patch = (
            ROOT / "patches/rexglue/0059-d3d12-isolated-draw-readback.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("QueueIsolatedReplayReadback", isolated_readback_patch)
        self.assertIn("GetCopyableFootprints", isolated_readback_patch)
        self.assertIn("D3DCopyTextureRegion", isolated_readback_patch)
        self.assertIn("D3DResolveSubresource", isolated_readback_patch)
        self.assertIn("failure_detail_out", isolated_readback_patch)
        self.assertIn("readback_result.detail", isolated_readback_patch)
        self.assertIn("GetCompletedSubmission", isolated_readback_patch)
        self.assertNotIn("AwaitAllQueueOperationsCompletion", isolated_readback_patch)
        self.assertNotIn("SetDrawSuppression", isolated_readback_patch)
        copy_position = isolated_readback_patch.index("D3DCopyTextureRegion")
        guest_draw_position = isolated_readback_patch.index(
            "render_target_cache_->EndIsolatedReplayTarget", copy_position
        )
        self.assertLess(copy_position, guest_draw_position)
        self.assertIn("captured_signature", scanner)
        self.assertIn("captured_frame", scanner)
        self.assertIn("captured_draw", scanner)

        visual_marker_patch = (
            ROOT / "patches/rexglue/0060-d3d12-isolated-draw-debug-markers.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("PinyonShift NR-02E isolated native draw", visual_marker_patch)
        self.assertIn("PinyonShift NR-02E authoritative Xenos draw", visual_marker_patch)
        self.assertEqual(visual_marker_patch.count("BeginDebugMarker"), 2)
        self.assertEqual(visual_marker_patch.count("EndDebugMarker"), 2)
        self.assertIn("reference_marker_requested", visual_marker_patch)
        self.assertNotIn("SetDrawSuppression", visual_marker_patch)
        self.assertIn("request.reference_marker_requested = true", scanner)
        self.assertIn(
            "request.requested = g_isolated_draw.prepared_candidate_eligible", scanner
        )
        self.assertIn("authoritative Xenos draw still follows unmodified", scanner)

        seeded_target_patch = (
            ROOT / "patches/rexglue/0061-d3d12-seeded-isolated-replay-targets.patch"
        ).read_text(encoding="utf-8")
        seeded_target_additions = "\n".join(
            line[1:]
            for line in seeded_target_patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertEqual(seeded_target_additions.count("D3DCopyResource"), 2)
        self.assertIn("guest_depth_state", seeded_target_additions)
        self.assertIn("guest_color_state", seeded_target_additions)
        self.assertNotIn("D3DClearRenderTargetView", seeded_target_additions)
        self.assertNotIn("D3DClearDepthStencilView", seeded_target_additions)
        self.assertNotIn("SetDrawSuppression", seeded_target_additions)

        visual_compare = (
            ROOT / "tools/compare-native-renderer-images.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon-shift.native-renderer-image-comparison.v1", visual_compare
        )
        self.assertIn('args.content == "depth"', visual_compare)
        self.assertIn("native.channels in (2, 4)", visual_compare)
        renderdoc_wrapper = (
            ROOT / "tools/capture-native-renderer-renderdoc.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Get-AuthenticodeSignature", renderdoc_wrapper)
        self.assertIn("CaptureDir must be below", renderdoc_wrapper)
        self.assertIn("RenderDoc exited without producing", renderdoc_wrapper)

        renderdoc_export = (
            ROOT / "tools/export-native-renderer-renderdoc.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon-shift.native-renderer-renderdoc-export.v1",
            renderdoc_export,
        )
        self.assertIn("GetRootActions", renderdoc_export)
        self.assertIn("SetFrameEvent", renderdoc_export)
        self.assertIn("SaveTexture", renderdoc_export)
        self.assertIn("GetDepthTarget", renderdoc_export)
        self.assertIn('basename + "-before.png"', renderdoc_export)
        self.assertIn('basename + "-depth-before.png"', renderdoc_export)
        self.assertIn('output_dir, "isolated-native"', renderdoc_export)
        self.assertIn('output_dir, "authoritative-xenos"', renderdoc_export)
        self.assertIn("authoritative Xenos marker follows", renderdoc_export)
        renderdoc_export_wrapper = (
            ROOT / "tools/export-native-renderer-renderdoc.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Get-AuthenticodeSignature", renderdoc_export_wrapper)
        self.assertIn("Capture must be below", renderdoc_export_wrapper)
        self.assertIn("OutputDir must be below", renderdoc_export_wrapper)
        self.assertIn("qrenderdoc exited without producing", renderdoc_export_wrapper)

        pass_trace = (
            ROOT / "tools/export-native-renderer-pass-trace.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon-shift.native-renderer-renderdoc-pass-trace.v1", pass_trace
        )
        self.assertIn("resource_payload_exported", pass_trace)
        self.assertIn("authoritative_candidate", pass_trace)
        self.assertNotIn("SaveTexture", pass_trace)
        pass_trace_wrapper = (
            ROOT / "tools/export-native-renderer-pass-trace.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Get-AuthenticodeSignature", pass_trace_wrapper)
        self.assertIn("@{ Name = 'Capture'", pass_trace_wrapper)
        self.assertIn("@{ Name = 'Output'", pass_trace_wrapper)
        self.assertIn('$($item.Name) must be below', pass_trace_wrapper)
        pass_inventory = (
            ROOT / "tools/build-native-renderer-pass-inventory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("isolated_native_draws_ignored", pass_inventory)
        self.assertIn('"suppression_eligible"] = False', pass_inventory)

        draw_state_planner = (
            ROOT / "tools/build-native-draw-state-contract.py"
        ).read_text(encoding="utf-8")
        self.assertIn("PHYSICAL_MASK = 0x1FFFFFFF", draw_state_planner)
        self.assertIn('"guest_resource_payload_read": False', draw_state_planner)
        self.assertIn('"native_upload": False', draw_state_planner)
        self.assertIn('"native_draw": False', draw_state_planner)
        self.assertIn('"suppression_allowed": False', draw_state_planner)
        self.assertIn('"xenos_authority": True', draw_state_planner)

    def test_census_ledger_tracks_exact_starting_baseline(self):
        ledger = (ROOT / "docs/native-renderer/RENDER_PASS_CENSUS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("cafc7233fef9e039f163d11023f40eccb22e8fc1", ledger)
        self.assertIn("f5337cdc947ff6d4c4196737e2c807a48f2a1fc2", ledger)
        self.assertIn("Unknown work stays on Xenos.", ledger)


if __name__ == "__main__":
    unittest.main()
