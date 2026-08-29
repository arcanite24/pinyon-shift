import json
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
        self.assertNotIn("g_semantic_instances = {};", source)
        self.assertNotIn("g_semantic_submissions = {};", source)
        self.assertIn(
            "std::memset(&g_draw_census, 0, sizeof(g_draw_census));", source
        )
        self.assertIn(
            "std::memset(&g_dependency_census, 0, sizeof(g_dependency_census));",
            source,
        )
        self.assertIn(
            "std::memset(g_semantic_instances.data(), 0, "
            "sizeof(g_semantic_instances));",
            source,
        )
        self.assertIn(
            "std::memset(g_semantic_submissions.data(), 0,\n"
            "                sizeof(g_semantic_submissions));",
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

    def test_procedural_model_semantic_extraction_is_bounded_and_passive(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        summarizer = (
            ROOT / "tools/summarize-native-renderer-semantic-instances.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveProceduralModelRenderItem"'),
            1,
        )
        hook = analysis.split(
            'name = "PinyonShiftObserveProceduralModelRenderItem"', 1
        )[0].rsplit("[[midasm_hook]]", 1)[1]
        self.assertIn("address = 0x8241741C", hook)
        self.assertIn("kSemanticInstanceCapacity = 4096", source)
        self.assertIn("kSemanticObservationPayloadBytes = 380", source)
        self.assertIn("LoadSemanticGuestWords", source)
        self.assertIn('"classification", "unclassified_material_or_state"', source)
        self.assertIn('{"fallback", "xenos_replay"}', source)
        self.assertIn('{"native_upload", "false"}', source)
        self.assertIn('{"native_draw", "false"}', source)
        self.assertIn('{"suppression_allowed", "false"}', source)
        self.assertNotIn("SetDrawSuppression", source)
        self.assertIn('"bounded_guest_read": True', summarizer)
        self.assertIn('"suppression_allowed": False', summarizer)

    def test_exact_pass_consumer_trace_is_bounded_and_fail_closed(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        summarizer = (
            ROOT / "tools/summarize-native-renderer-pass-consumers.py"
        ).read_text(encoding="utf-8")

        self.assertIn("kPassConsumerDetailLimit = 64", source)
        self.assertIn("kPassConsumerSignatureCapacity = 1024", source)
        self.assertIn("CopyReadsPassTarget", source)
        self.assertIn("copy.surface_info != target.surface_info", source)
        self.assertIn("copy.color_info[source] == target.color_info[source]", source)
        self.assertIn("copy.depth_info == target.depth_info", source)
        self.assertIn('"native_renderer.census.pass_family_resolve"', source)
        self.assertIn('"native_renderer.census.pass_family_consumer"', source)
        self.assertIn(
            '"native_renderer.census.pass_family_consumer_summary"', source
        )
        self.assertIn(
            '"native_renderer.census.pass_family_consumer_signature"', source
        )
        self.assertIn('"prepared_metadata"', source)
        self.assertIn('"family_base_fetch_mask"', source)
        self.assertIn('"family_mip_fetch_mask"', source)
        self.assertIn('"prepared_metadata_count"', source)
        self.assertIn('"prepared_metadata_missing"', source)
        self.assertIn('"unprepared_consumer_draws"', source)
        self.assertIn('"unprepared_consumer_references"', source)
        self.assertIn('{"xenos_draw", "preserved"}', source)
        self.assertIn('{"suppression_eligible", "false"}', source)
        self.assertIn('"unobserved_means_independent": False', summarizer)
        self.assertIn('"suppression_allowed": False', summarizer)
        self.assertIn('"later_gpu_consumers": later_gpu_consumer_gate', summarizer)

    def test_procedural_model_submission_contract_is_bounded_and_passive(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        summarizer = (
            ROOT / "tools/summarize-native-renderer-semantic-submissions.py"
        ).read_text(encoding="utf-8")

        expected_hooks = {
            "PinyonShiftObserveProceduralModelPrimaryResourceBinding": "0x82417A74",
            "PinyonShiftObserveProceduralModelSecondaryResourceBinding": "0x82417A9C",
            "PinyonShiftObserveProceduralModelGeometrySubmission": "0x82417B60",
        }
        for name, address in expected_hooks.items():
            self.assertEqual(analysis.count(f'name = "{name}"'), 1)
            hook = analysis.split(f'name = "{name}"', 1)[0].rsplit(
                "[[midasm_hook]]", 1
            )[1]
            self.assertIn(f"address = {address}", hook)
        self.assertIn("kSemanticSubmissionCapacity = 8192", source)
        self.assertIn("kSemanticSubmissionMaximumPayloadBytes = 56", source)
        self.assertIn("runtime_record_24_default", source)
        self.assertIn("runtime_record_28_32", source)
        self.assertIn('"classification", "structural_resource_and_geometry_submission"', source)
        self.assertIn('{"fallback", "xenos_replay"}', source)
        self.assertIn('{"native_upload", "false"}', source)
        self.assertIn('{"native_draw", "false"}', source)
        self.assertIn('{"suppression_allowed", "false"}', source)
        self.assertIn('"bounded_guest_read": True', summarizer)
        self.assertIn('"suppression_allowed": False', summarizer)

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

    def test_exact_pass_guest_cpu_visibility_is_bounded_and_passive(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT / "patches/rexglue/0074-physical-memory-read-observer.patch"
        ).read_text(encoding="utf-8")
        summarizer = (
            ROOT / "tools/summarize-native-renderer-pass-consumers.py"
        ).read_text(encoding="utf-8")

        self.assertIn("kGuestCpuVisibilityTargetCapacity = 64", source)
        self.assertIn("RegisterPhysicalMemoryAccessCallback", source)
        self.assertIn("EnablePhysicalMemoryAccessCallbacks", source)
        self.assertIn('"native_renderer.census.pass_family_guest_cpu_summary"', source)
        self.assertIn('"native_renderer.census.pass_family_guest_cpu_target"', source)
        self.assertIn('{"xenos_draw", "preserved"}', source)
        self.assertIn('{"suppression_eligible", "false"}', source)
        self.assertIn("PhysicalMemoryAccessCallback", patch)
        self.assertIn("notify_on_access", patch)
        self.assertIn("notify_access_observers", patch)
        self.assertIn("runtime::ThreadState::Get() != nullptr", patch)
        self.assertIn("One-shot", patch)
        self.assertNotIn("SetDrawSuppression", patch)
        self.assertIn('"guest_cpu_visibility": guest_cpu_gate', summarizer)
        self.assertIn('"suppression_allowed": False', summarizer)

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

    def test_draw_packet_provenance_is_exact_bounded_and_passive(self):
        patch = (
            ROOT
            / "patches/rexglue/0080-graphics-draw-packet-provenance.patch"
        ).read_text(encoding="utf-8")
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("packet_physical_address", patch)
        self.assertIn("reader->buffer()", patch)
        self.assertIn("reader->read_offset()", patch)
        self.assertIn("memory_->physical_membase()", patch)
        self.assertIn("observation.packet_physical_address =", patch)
        self.assertIn("observation_packet_physical_address_", patch)
        self.assertIn("kTitlePacketProvenanceCapacity = 16384", source)
        self.assertIn("kTitleDrawProvenanceCapacity = 4096", source)
        self.assertIn("kTitleOriginStackCapacity = 32", source)
        self.assertIn("exact_physical_pm4_header_address", source)
        self.assertIn("GetPhysicalAddress(packet_guest_address)", source)
        self.assertIn("packet_accounting_complete", source)
        self.assertNotIn("g_title_packet_provenance = {};", source)
        self.assertNotIn("g_title_draw_provenance = {};", source)
        report = (ROOT / "tools/create-crash-report.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("title_draw_provenance", report)
        self.assertIn(
            "native_renderer.discovery.title_provenance_summary", report
        )
        self.assertIn("packet_address_failures", report)
        self.assertIn('address = 0x82410328', analysis)
        self.assertIn('address = 0x829F7CB0', analysis)
        for forbidden in (
            "SetDrawSuppression",
            "SetCopySuppression",
            "guest_payload_read\", \"true",
        ):
            self.assertNotIn(forbidden, patch + source + analysis)

    def test_d3d12_draw_outcomes_cover_every_issue_draw_exit(self):
        patch = (
            ROOT
            / "patches/rexglue/0081-d3d12-draw-outcome-observer.patch"
        ).read_text(encoding="utf-8")
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        for token in (
            "GraphicsDrawOutcomeObservation",
            "SetDrawOutcomeObserver",
            "kEdramCopy",
            "kPipelinePending",
            "kCompleted",
            "observation_packet_physical_address_",
        ):
            self.assertIn(token, patch)
        self.assertEqual(patch.count("return observe_draw_outcome("), 21)
        self.assertIn("void ObserveDrawOutcome(", source)
        self.assertIn("backend_draw_outcome_mismatches", source)
        self.assertIn("backend_draw_outcome_missing", source)
        self.assertIn("SetDrawOutcomeObserver(&ObserveDrawOutcome)", source)
        self.assertIn("SetDrawOutcomeObserver(nullptr)", source)
        self.assertNotIn("suppression_allowed\", \"true", patch + source)

    def test_draw_command_buffer_lineage_is_exact_bounded_and_passive(self):
        patch = (
            ROOT
            / "patches/rexglue/0082-graphics-command-buffer-lineage.patch"
        ).read_text(encoding="utf-8")
        patch += (
            ROOT
            / "patches/rexglue/0083-graphics-indirect-buffer-observer.patch"
        ).read_text(encoding="utf-8")
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        report = (ROOT / "tools/create-crash-report.ps1").read_text(
            encoding="utf-8"
        )
        for token in (
            "command_buffer_physical_address",
            "command_buffer_length_dwords",
            "command_buffer_parent_packet_physical_address",
            "command_buffer_root_physical_address",
            "command_buffer_depth",
            "ObservationCommandBufferContext",
            "ExecutePrimaryBuffer",
            "ExecuteIndirectBuffer",
            "ExecutePacket(uint32_t ptr, uint32_t count)",
            "GraphicsIndirectBufferObservation",
            "SetIndirectBufferObserver",
            "indirect_buffer_observer",
            "entering = true",
            "entering = false",
        ):
            self.assertIn(token, patch)
        self.assertGreaterEqual(
            patch.count("previous_observation_command_buffer"), 6
        )
        self.assertIn("kCommandBufferLineageCapacity = 4096", source)
        self.assertIn("HasValidCommandBufferLineage", source)
        self.assertIn("packet_offset_bytes", source)
        self.assertIn("sample_command_buffer_length_dwords", source)
        self.assertIn("min_command_buffer_length_dwords", source)
        self.assertIn("max_command_buffer_length_dwords", source)
        self.assertIn("min_parent_root_offset_bytes", source)
        self.assertIn("max_parent_root_offset_bytes", source)
        self.assertIn("g_title_indirect_buffers_open", source)
        self.assertIn("indirect_buffers_open_at_shutdown", source)
        self.assertIn("kTitleIndirectPacketWays = 4", source)
        self.assertIn("title_indirect_packet_evictions", source)
        self.assertIn("entry.occupied = false", source)
        self.assertIn("g_command_buffer_lineage_installed", source)
        self.assertIn("g_command_buffer_lineage_memory", source)
        self.assertIn("constructor_store_address", source)
        self.assertIn("CurrentTitleIndirectBuffer", source)
        self.assertIn("constructor_return_address", source)
        self.assertIn("indirect_constructor_stack_faults", source)
        self.assertIn("kIndirectOwnerStackCapacity = 32", source)
        self.assertIn("owner_return_address", source)
        self.assertIn("indirect_owner_stack_faults", source)
        self.assertIn("indirect_constructor_owner_mismatches", source)
        self.assertIn("kIndirectProducerStackCapacity = 32", source)
        self.assertIn("producer_return_address", source)
        self.assertIn("indirect_producer_stack_faults", source)
        self.assertIn("indirect_owner_producer_mismatches", source)
        self.assertIn("kIndirectContextStackCapacity = 32", source)
        self.assertIn("ExpectedIndirectContextFunction", source)
        self.assertIn("DeriveIndirectContextRoot", source)
        self.assertIn("context_function_address", source)
        self.assertIn("sample_context_root_address", source)
        self.assertIn("indirect_context_stack_faults", source)
        self.assertIn("kSemanticReceiverLifecycleCapacity = 1024", source)
        self.assertIn("FindOrClaimSemanticReceiverLifecycle", source)
        self.assertIn("ResolveSemanticReceiver", source)
        self.assertIn("semantic_receiver_unregistered_dispatches", source)
        self.assertIn("semantic_visibility_epoch", source)
        self.assertIn("semantic_render_state_epoch", source)
        self.assertIn("BeginSemanticReceiverStage", source)
        self.assertIn("semantic_stage_unknown_receivers", source)
        self.assertIn(
            "proceduralGeometry::CProceduralModels", source
        )
        self.assertIn("indirect_producer_context_mismatches", source)
        self.assertIn(
            "std::atomic<uint64_t> g_indirect_producer_entries", source
        )
        self.assertIn("SetIndirectBufferObserver(&ObserveIndirectBuffer)", source)
        self.assertIn("SetIndirectBufferObserver(nullptr)", source)
        self.assertIn(
            "exact_title_store_to_backend_nested_command_buffer_shape", source
        )
        self.assertIn(
            "native_renderer.discovery.command_buffer_lineage_summary",
            source,
        )
        self.assertIn("command_buffer_lineage", report)
        for forbidden in (
            "SetDrawSuppression",
            "SetCopySuppression",
            'guest_payload_read\", \"true',
            'suppression_allowed\", \"true',
        ):
            self.assertNotIn(forbidden, patch + source)

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

    def test_retained_pass_preview_is_explicit_and_preserves_xenos(self):
        patch = (
            ROOT / "patches/rexglue/0065-d3d12-retained-pass-preview.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("NativeGuestOutputDrawRetainedPass", patch)
        self.assertIn("BeginIsolatedReplayPreview", patch)
        self.assertIn("EndIsolatedReplayPreview", patch)
        self.assertIn("native_guest_output_retained_pass_cs", patch)
        self.assertIn("DXGI_FORMAT_R16G16B16A16_FLOAT", patch)
        self.assertIn("isolated_replay_preview_resolved_target_", patch)
        self.assertIn("D3D12_RESOURCE_STATE_RESOLVE_SOURCE", patch)
        self.assertIn("D3D12_RESOURCE_STATE_RESOLVE_DEST", patch)
        self.assertIn("D3DResolveSubresource", patch)
        self.assertIn("D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE", patch)
        self.assertIn("kGuestOutputInternalState", patch)
        self.assertNotIn("SetDrawSuppression", patch)

        source = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn('mode == "diagnostic_retained_pass"', source)
        self.assertIn("context.draw_retained_pass(context, retained_mode)", source)
        self.assertIn('"retained_pass_unavailable"', source)
        self.assertIn('{"suppression", "disabled"}', source)

        settings = (ROOT / "tools/set-graphics-experiment.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'diagnostic_retained_pass'", settings)

        report = (ROOT / "tools/create-crash-report.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'native_renderer.output.waiting'", report)
        self.assertIn("waiting_reason", report)

    def test_retained_pass_requires_current_frame_publication(self):
        patch = (
            ROOT
            / "patches/rexglue/0067-d3d12-retained-pass-frame-freshness.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("retained_pass_frame_sequence", patch)
        self.assertIn("isolated_replay_preview_frame_sequence_", patch)
        self.assertIn("required_frame_sequence", patch)
        self.assertIn(
            "isolated_replay_preview_frame_sequence_ != required_frame_sequence",
            patch,
        )
        self.assertIn(
            "EndIsolatedReplayTarget(\n+            isolated_draw_request.frame_sequence)",
            patch,
        )
        self.assertNotIn("SetDrawSuppression", patch)

        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertGreaterEqual(
            hooks.count("request.frame_sequence = g_isolated_draw.frame"), 3
        )

        output = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "context.retained_pass_frame_sequence == context.frame_sequence",
            output,
        )
        self.assertIn('"retained_pass_stale"', output)
        self.assertIn('{"fallback", "xenos"}', output)
        self.assertIn('{"suppression", "disabled"}', output)

    def test_continuous_composition_uses_a_private_display_target(self):
        patch = (
            ROOT / "patches/rexglue/0068-d3d12-native-display-target.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("native_guest_output_display_target_", patch)
        self.assertIn("D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS", patch)
        self.assertIn("D3D12_RESOURCE_STATE_COPY_SOURCE", patch)
        self.assertIn("D3D12_RESOURCE_STATE_COPY_DEST", patch)
        self.assertIn(
            "resource, native_guest_output_display_target_.Get()", patch
        )
        self.assertIn("resources_for_deletion_.emplace_back", patch)
        self.assertIn("native_guest_output_display_target_.Reset()", patch)
        self.assertNotIn("SetDrawSuppression", patch)

        output = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn('"private_display_target"', output)
        self.assertIn('{"xenos_draw", "preserved"}', output)
        self.assertIn('{"suppression", "disabled"}', output)

        report = (ROOT / "tools/create-crash-report.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("composition = $null", report)
        self.assertIn(
            "$nativeRenderer.composition = [string]$event.composition", report
        )

    def test_dual_path_comparison_has_one_controlled_output_authority(self):
        patch = (
            ROOT / "patches/rexglue/0069-d3d12-dual-path-comparison.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("NativeGuestOutputRetainedPassMode", patch)
        self.assertIn("kCompareNative", patch)
        self.assertIn("kCompareXenos", patch)
        self.assertIn("PinyonShift NR-04C native display composition", patch)
        self.assertIn("PinyonShift NR-04C native output selection", patch)
        self.assertIn("if (present_native)", patch)
        additions = "\n".join(
            line[1:]
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertEqual(additions.count("D3DCopyResource"), 1)
        self.assertNotIn("SetDrawSuppression", patch)

        output = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn('mode == "comparison_native"', output)
        self.assertIn('mode == "comparison_xenos"', output)
        self.assertIn('"selected_output"', output)
        self.assertIn('"authority"', output)
        self.assertIn('{"xenos_draw", "preserved"}', output)
        self.assertIn('{"suppression", "disabled"}', output)

        settings = (ROOT / "tools/set-graphics-experiment.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'SetRenderer'", settings)
        self.assertIn("'comparison_native'", settings)
        self.assertIn("'comparison_xenos'", settings)

        capture = (
            ROOT / "tools/capture-native-renderer-output-comparison.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Get -StateRoot", capture)
        self.assertIn("-Action SetRenderer", capture)
        self.assertIn("finally", capture)
        self.assertIn("$originalRenderer", capture)

        exporter = (
            ROOT / "tools/export-native-renderer-output-comparison.py"
        ).read_text(encoding="utf-8")
        self.assertIn("pinyon-shift.native-output-comparison.v1", exporter)
        self.assertIn("copy.copySource", exporter)
        self.assertIn("copy.copyDestination", exporter)
        self.assertIn("copy.eventId - 1", exporter)
        self.assertIn("GPUCounter.EventGPUDuration", exporter)
        self.assertIn("native-private.png", exporter)
        self.assertIn("xenos-output.png", exporter)

        wrapper = (
            ROOT / "tools/export-native-renderer-output-comparison.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Get-AuthenticodeSignature", wrapper)
        self.assertIn("Capture must be below", wrapper)
        self.assertIn("OutputDir must be below", wrapper)
        self.assertIn("-WindowStyle Hidden", wrapper)

        report = (ROOT / "tools/create-crash-report.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("selected_output = $null", report)
        self.assertIn("authority = $null", report)

    def test_native_gpu_timing_is_async_bounded_and_non_suppressing(self):
        patch = (
            ROOT / "patches/rexglue/0070-d3d12-native-gpu-timing.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("D3D12_QUERY_HEAP_TYPE_TIMESTAMP", patch)
        self.assertIn("kNativeGuestOutputGpuQueriesPerFrame = 5", patch)
        self.assertIn("std::array<NativeGuestOutputGpuTimingSlot", patch)
        self.assertIn("slot.submission > submission_completed_", patch)
        self.assertIn("D3DResolveQueryData", patch)
        self.assertIn("PROFILE_GUEST_FRAME_GPU_TIME_NS", patch)
        self.assertIn("PROFILE_NATIVE_COMPOSITION_GPU_TIME_NS", patch)
        self.assertIn("PROFILE_NATIVE_SELECTION_GPU_TIME_NS", patch)
        self.assertIn("PROFILE_NATIVE_GPU_TIMING_DROP", patch)
        self.assertNotIn("WaitForSingleObject", patch)
        self.assertNotIn("SetDrawSuppression", patch)

        summarizer = (ROOT / "tools/summarize-performance.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("NATIVE_GPU_TIMING_COLUMNS", summarizer)
        self.assertIn('"native_renderer_gpu_timing"', summarizer)

    def test_suppression_admission_is_fail_closed_and_non_mutating(self):
        evaluator = (
            ROOT / "tools/evaluate-native-renderer-suppression.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"guest_cpu_visibility"', evaluator)
        self.assertIn('"later_gpu_consumers"', evaluator)
        self.assertIn('"rollback_switch"', evaluator)
        self.assertIn('"suppression_allowed": False', evaluator)
        self.assertIn('"draw_suppression_implemented": False', evaluator)
        self.assertIn('"resolve_suppression_implemented": False', evaluator)
        self.assertNotIn("SetDrawSuppression", evaluator)

    def test_publication_qualification_preserves_consumers_fail_closed(self):
        qualifier = (
            ROOT / "tools/qualify-native-renderer-publication.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"pinyon-shift.native-renderer-publication-qualification.v1"',
            qualifier,
        )
        self.assertIn('"later_gpu_consumers": "pass"', qualifier)
        self.assertIn('"xenos_consumers_preserved": True', qualifier)
        self.assertIn('"suppression_allowed": False', qualifier)

        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "pinyon_shift_native_renderer_sky_horizon_suppression", hooks
        )
        self.assertIn('"armed_experimental"', hooks)
        self.assertIn('"fail_closed_follower_draw"', hooks)
        self.assertIn('"follower_after_publication_only"', hooks)
        self.assertIn('"resolve_suppression", "false"', hooks)
        self.assertNotIn("SetDrawSuppression", hooks)

        patch = (
            ROOT
            / "patches/rexglue/0079-d3d12-fail-closed-retained-pass-suppression.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("suppress_guest_draw_if_published", patch)
        self.assertIn("guest_draw_suppressed", patch)
        self.assertIn("PublishIsolatedReplayTarget", patch)
        self.assertIn("if (!suppress_guest_draw)", patch)
        self.assertNotIn("SetCopySuppression", patch)

        settings = (ROOT / "tools/set-graphics-experiment.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'SetSkyHorizonSuppression'", settings)
        self.assertIn("pinyon_shift_config_schema = 11", settings)

    def test_consumer_family_classifier_is_exact_and_fail_closed(self):
        classifier = json.loads(
            (ROOT / "config/native-renderer/consumer-family-classifier.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "pinyon-shift.native-renderer-consumer-family-classifier.v1",
            classifier["schema"],
        )
        self.assertEqual(38, len(classifier["rules"]))
        self.assertEqual(
            38, len({rule["shader_family_id"] for rule in classifier["rules"]})
        )
        self.assertTrue(
            all(
                rule["semantic_role"] == "retained_unknown"
                for rule in classifier["rules"]
            )
        )
        self.assertTrue(
            all(rule["native_coverage"] is False for rule in classifier["rules"])
        )

    def test_suppression_switch_spec_is_default_off_and_fail_closed(self):
        switches = json.loads(
            (ROOT / "config/native-renderer/suppression-switches.json").read_text(
                encoding="utf-8"
            )
        )
        family = switches["families"][0]
        self.assertFalse(family["default_enabled"])
        self.assertTrue(family["independent"])
        self.assertEqual("implemented", family["implementation_status"])
        self.assertEqual(
            "pinyon_shift_native_renderer_sky_horizon_suppression",
            family["cvar"],
        )
        self.assertTrue(family["draw_suppression_implemented"])
        self.assertFalse(family["resolve_suppression_implemented"])
        self.assertTrue(family["state_yield_implemented"])
        self.assertTrue(family["state_yield_qualified"])
        self.assertEqual("consecutive_publication_warmup", family["state_gate"])
        self.assertEqual(8, family["warmup_frames"])
        self.assertEqual(120, family["failure_cooldown_frames"])
        self.assertTrue(family["guest_side_effects_preserved"])
        graphics_hooks = (
            ROOT / "src" / "native_renderer" / "graphics_hooks.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("PrepareSuppressionAttempt", graphics_hooks)
        self.assertIn("EnterSuppressionCooldown", graphics_hooks)
        self.assertIn("consecutive_publication_warmup", graphics_hooks)
        self.assertIn("backend_ignored_state_yield", graphics_hooks)
        qualifier = (
            ROOT / "tools" / "qualify-native-renderer-state-yield.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon-shift.native-renderer-state-yield-qualification.v1",
            qualifier,
        )
        self.assertIn("unexpected_suppressions", qualifier)
        self.assertTrue(family["anchor_draw_preserved"])
        self.assertEqual(
            "execute_original_follower", family["publication_failure_behavior"]
        )

    def test_complete_pass_export_spans_anchor_and_follower(self):
        exporter = (
            ROOT / "tools/export-native-renderer-renderdoc.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT / "tools/export-native-renderer-renderdoc.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("PASS_NATIVE_ANCHOR_MARKER", exporter)
        self.assertIn("PASS_XENOS_ANCHOR_MARKER", exporter)
        self.assertIn("PASS_NATIVE_FOLLOWER_MARKER", exporter)
        self.assertIn("PASS_XENOS_FOLLOWER_MARKER", exporter)
        self.assertIn("_export_pass_span", exporter)
        self.assertIn('"draw_count": 2', exporter)
        self.assertIn('"suppression_allowed": False', exporter)
        self.assertIn("[switch]$CompletePass", wrapper)
        self.assertIn("PINYON_SHIFT_RENDERDOC_COMPLETE_PASS", wrapper)
        self.assertNotIn("SetDrawSuppression", exporter)

    def test_consumer_family_marker_is_exact_passive_and_exportable(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT / "patches/rexglue/0075-d3d12-consumer-family-marker.patch"
        ).read_text(encoding="utf-8")
        capture = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        exporter = (
            ROOT / "tools/export-native-renderer-renderdoc.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT / "tools/export-native-renderer-renderdoc.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY", hooks)
        for field in (
            "vertex_shader_hash",
            "pixel_shader_hash",
            "vertex_specialization_mask",
            "pixel_specialization_mask",
        ):
            self.assertIn(field, hooks)
        self.assertIn("consumer_reference_marker_requested", hooks)
        self.assertIn("authoritative_draw_marker_only", hooks)
        self.assertIn("consumer_reference_marker_requested", patch)
        self.assertIn(
            "PinyonShift NR-00E authoritative consumer family draw", patch
        )
        self.assertNotIn("SetDrawSuppression", hooks + patch)
        self.assertNotIn("SetCopySuppression", hooks + patch)
        self.assertIn("[string]$ConsumerFamily", capture)
        self.assertIn("PINYON_SHIFT_RENDERDOC_CONSUMER_FAMILY", wrapper)
        self.assertIn("CONSUMER_FAMILY_SCHEMA", exporter)
        self.assertIn("operator_review_required", exporter)
        self.assertIn("MAX_CONSUMER_MARKER_EVENT_IDS = 64", exporter)

    def test_consumer_family_readback_is_paired_bounded_and_passive(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT / "patches/rexglue/0076-d3d12-consumer-family-readback.patch"
        ).read_text(encoding="utf-8")
        capture = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        analyzer = (
            ROOT / "tools/analyze-native-renderer-consumer-readback.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR", hooks
        )
        self.assertIn("consumer_reference_readback_requested", patch)
        self.assertIn("QueueGuestConsumerColorReadback", patch)
        self.assertIn("guest_consumer_before_readback_", patch)
        self.assertIn("guest_consumer_after_readback_", patch)
        self.assertIn("before_after_color", hooks)
        self.assertIn("[string]$ConsumerReadbackDir", capture)
        self.assertIn("operator_review_required", analyzer)
        self.assertIn('"xenos_draw_preserved": True', analyzer)
        self.assertIn('"draw_suppression": False', analyzer)
        self.assertIn('"resolve_suppression": False', analyzer)
        self.assertIn('"suppression_allowed": False', analyzer)
        self.assertNotIn("SetDrawSuppression", hooks + patch + analyzer)
        self.assertNotIn("SetCopySuppression", hooks + patch + analyzer)

    def test_consumer_family_corpus_captures_depth_without_suppression(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0077-d3d12-consumer-family-depth-corpus.patch"
        ).read_text(encoding="utf-8")
        census = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        renderdoc = (
            ROOT / "tools/capture-native-renderer-renderdoc.ps1"
        ).read_text(encoding="utf-8")
        analyzer = (
            ROOT / "tools/analyze-native-renderer-consumer-readback.py"
        ).read_text(encoding="utf-8")

        self.assertIn("kMaximumConsumerReadbackSamples = 16", hooks)
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES", hooks
        )
        self.assertIn("consumer_reference_depth_readback_requested", patch)
        self.assertIn("QueueGuestConsumerDepthReadback", patch)
        self.assertIn("guest_consumer_before_depth_readback_", patch)
        self.assertIn("guest_consumer_after_depth_readback_", patch)
        self.assertIn("before_after_color_and_depth_stencil", hooks)
        self.assertIn("[ValidateRange(1, 16)]", census)
        self.assertIn("[ValidateRange(1, 16)]", renderdoc)
        self.assertIn("consumer-family-contribution-corpus.v1", analyzer)
        self.assertIn("all_samples_no_attachment_delta", analyzer)
        self.assertIn("operator_review_required", analyzer)
        self.assertNotIn("SetDrawSuppression", hooks + patch + analyzer)
        self.assertNotIn("SetCopySuppression", hooks + patch + analyzer)

    def test_retained_pass_publication_preserves_xenos_side_effects(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0078-d3d12-retained-pass-output-publication.patch"
        ).read_text(encoding="utf-8")
        census = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        renderdoc = (
            ROOT / "tools/capture-native-renderer-renderdoc.ps1"
        ).read_text(encoding="utf-8")
        summarizer = (
            ROOT / "tools/summarize-native-renderer-pass-publication.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS", hooks
        )
        self.assertIn("publication_config", hooks)
        self.assertIn("publication_summary", hooks)
        self.assertIn("guest_target_content", hooks)
        self.assertIn("publish_to_guest_requested", patch)
        self.assertIn("PublishIsolatedReplayTarget", patch)
        self.assertIn("kTargetMismatch", patch)
        self.assertIn("isolated_replay_recorded", patch)
        self.assertIn("D3DCopyResource(guest_depth->resource()", patch)
        self.assertIn("D3DCopyResource(guest_color->resource()", patch)
        self.assertIn(
            "PinyonShift NR-04D native retained-pass publication", patch
        )
        self.assertIn("[switch]$PublishRetainedPass", census)
        self.assertIn("[switch]$PublishRetainedPass", renderdoc)
        self.assertIn("native-renderer-pass-publication.v1", summarizer)
        self.assertIn("native_retained_pass", summarizer)
        self.assertIn('"suppression_allowed": False', summarizer)
        self.assertIn('"later_gpu_consumers_gate": "qualification_required"', summarizer)
        self.assertIn('"xenos_draw", "preserved"', hooks)
        self.assertIn('"draw_suppression", "false"', hooks)
        self.assertIn('"resolve_suppression", "false"', hooks)
        for source in (hooks, patch):
            self.assertNotIn("SetDrawSuppression", source)
            self.assertNotIn("SetCopySuppression", source)

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
        self.assertIn("candidate.sample = observation;", source)
        self.assertIn("g_pending_candidate = candidate;", source)
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

        auto_index_replay_patch = (
            ROOT / "patches/rexglue/0062-d3d12-isolated-auto-index-replay.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("D3DDrawInstanced", auto_index_replay_patch)
        self.assertIn("isolated native auto-index draw", auto_index_replay_patch)
        self.assertIn("authoritative Xenos auto-index draw", auto_index_replay_patch)
        self.assertNotIn("SetDrawSuppression", auto_index_replay_patch)
        self.assertIn("SourceSelect::kAutoIndex", scanner)

        retained_pass_patch = (
            ROOT
            / "patches/rexglue/0063-d3d12-retained-isolated-pass-target.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("ResumeIsolatedReplayTarget", retained_pass_patch)
        self.assertIn("reuse_target", retained_pass_patch)
        self.assertIn("isolated native pass anchor", retained_pass_patch)
        self.assertIn("isolated native pass follower", retained_pass_patch)
        self.assertNotIn("SetDrawSuppression", retained_pass_patch)
        self.assertIn("request.retain_target = true", scanner)
        self.assertIn("request.reuse_target = true", scanner)
        self.assertIn("native_renderer.isolated_pass.result", scanner)
        self.assertIn("native_renderer.isolated_pass.repeat", scanner)
        repeat_request = scanner.split(
            "} else if (!g_isolated_draw.pass_repeat_reported) {", 1
        )[1].split("}", 1)[0]
        self.assertNotIn("captured_frame =", repeat_request)
        self.assertNotIn("captured_draw =", repeat_request)

        paired_readback_patch = (
            ROOT
            / "patches/rexglue/0071-d3d12-paired-pass-color-readback.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("reference_readback_requested", paired_readback_patch)
        self.assertIn("QueueGuestColorReadback", paired_readback_patch)
        self.assertIn("guest_reference_readback_", paired_readback_patch)
        self.assertIn("GetCompletedSubmission", paired_readback_patch)
        self.assertNotIn("AwaitAllQueueOperationsCompletion", paired_readback_patch)
        self.assertNotIn("SetDrawSuppression", paired_readback_patch)
        marker_end = paired_readback_patch.index(
            "deferred_command_list_.EndDebugMarker"
        )
        xenos_readback = paired_readback_patch.index(
            "QueueGuestColorReadback", marker_end
        )
        self.assertLess(marker_end, xenos_readback)
        self.assertIn("CompleteIsolatedReferenceReadback", scanner)
        self.assertIn("request.reference_readback_requested", scanner)
        self.assertIn('readback, "xenos"', scanner)
        self.assertIn('"suppression_eligible", "false"', scanner)

        depth_readback_patch = (
            ROOT
            / "patches/rexglue/0072-d3d12-paired-pass-depth-readback.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("QueueIsolatedReplayDepthReadback", depth_readback_patch)
        self.assertIn("QueueGuestDepthReadback", depth_readback_patch)
        self.assertIn("plane_row_sizes", depth_readback_patch)
        self.assertIn("GetCopyableFootprints", depth_readback_patch)
        self.assertIn(
            "complete_isolated_readback(isolated_replay_depth_readback_)",
            depth_readback_patch,
        )
        self.assertIn(
            "complete_isolated_readback(guest_depth_reference_readback_)",
            depth_readback_patch,
        )
        self.assertNotIn("AwaitAllQueueOperationsCompletion", depth_readback_patch)
        self.assertNotIn("SetDrawSuppression", depth_readback_patch)
        msaa_depth_patch = (
            ROOT / "patches/rexglue/0073-d3d12-msaa-depth-readback.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("Texture2DMS<float> source_depth", msaa_depth_patch)
        self.assertIn("Texture2DMS<uint2> source_stencil", msaa_depth_patch)
        self.assertIn("depth32_stencil8_sample_tuples", scanner)
        self.assertIn("sample_count", msaa_depth_patch)
        self.assertIn("D3DCopyBufferRegion", msaa_depth_patch)
        self.assertIn("GetCurrentSubmission", msaa_depth_patch)
        self.assertNotIn("AwaitAllQueueOperationsCompletion", msaa_depth_patch)
        self.assertNotIn("SetDrawSuppression", msaa_depth_patch)
        self.assertIn("request.depth_readback_requested", scanner)
        self.assertIn("request.reference_depth_readback_requested", scanner)
        self.assertIn("CompleteIsolatedReferenceDepthReadback", scanner)
        self.assertIn('"capture_content", "depth_stencil"', scanner)

        texture_resource_patch = (
            ROOT
            / "patches/rexglue/0064-d3d12-native-texture-resource-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("GraphicsNativeTextureSetObservation", texture_resource_patch)
        self.assertIn("GraphicsNativeTextureRetain", texture_resource_patch)
        self.assertIn("GraphicsNativeTextureRelease", texture_resource_patch)
        self.assertIn("ObserveNativeTextures", texture_resource_patch)
        self.assertIn("texture_cache_->RequestTextures", texture_resource_patch)
        self.assertIn("completed_submission", texture_resource_patch)
        self.assertNotIn("SetDrawSuppression", texture_resource_patch)
        texture_bridge = (
            ROOT / "src/native_renderer/texture_resource_bridge.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon_shift_native_renderer_texture_bridge, false", texture_bridge
        )
        self.assertIn('"xenos_draw", "preserved"', texture_bridge)
        self.assertIn('"suppression", "disabled"', texture_bridge)
        self.assertIn("resource.retain(resource.resource)", texture_bridge)
        self.assertIn("retained->second.release", texture_bridge)
        self.assertIn("IsRetainedPassCandidate", texture_bridge)
        self.assertIn("observed_resource_count_", texture_bridge)
        self.assertIn("observed < 16", texture_bridge)
        self.assertIn("last_summary_submission_ + 300", texture_bridge)

        resolve_resource_patch = (
            ROOT
            / "patches/rexglue/0066-d3d12-native-resolve-provenance-observer.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("GraphicsNativeResolveObserver", resolve_resource_patch)
        self.assertIn("SetNativeResolveObserver", resolve_resource_patch)
        self.assertIn("native_resolve_observer", resolve_resource_patch)
        self.assertIn("guest_row_pitch_bytes", resolve_resource_patch)
        self.assertIn("copy_observer || native_resolve_observer", resolve_resource_patch)
        self.assertIn("current_submission", resolve_resource_patch)
        self.assertIn("completed_submission", resolve_resource_patch)
        self.assertNotIn("SetDrawSuppression", resolve_resource_patch)

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
        self.assertIn("PassAnchorSignature and IsolatedDrawDir", renderdoc_wrapper)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE", renderdoc_wrapper)
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
        self.assertIn("PINYON_SHIFT_RENDERDOC_NATIVE_MARKER", renderdoc_export)
        self.assertIn("PINYON_SHIFT_RENDERDOC_XENOS_MARKER", renderdoc_export)
        renderdoc_export_wrapper = (
            ROOT / "tools/export-native-renderer-renderdoc.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Get-AuthenticodeSignature", renderdoc_export_wrapper)
        self.assertIn("Capture must be below", renderdoc_export_wrapper)
        self.assertIn("OutputDir must be below", renderdoc_export_wrapper)
        self.assertIn("PINYON_SHIFT_RENDERDOC_NATIVE_MARKER", renderdoc_export_wrapper)
        self.assertIn("PINYON_SHIFT_RENDERDOC_XENOS_MARKER", renderdoc_export_wrapper)
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
