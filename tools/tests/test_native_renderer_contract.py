import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererContractTests(unittest.TestCase):


    def test_continuous_shadow_replay_is_reconciled_and_safe(self) -> None:
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        start = source.index("void CompleteIsolatedShadowReplay(")
        end = source.index(
            "void RecordVisibilityShadowReplaySignature(", start
        )
        completion = source[start:end]
        self.assertIn("shadow_replay_recorded", completion)
        self.assertIn("shadow_replay_target_failures", completion)
        self.assertIn("shadow_replay_unsupported", completion)
        self.assertNotIn("RecordEvent", completion)
        self.assertIn(
            '"native_renderer.isolated_draw.shadow_replay_summary"', source
        )
        self.assertIn('"accounting_complete"', source)
        self.assertIn('{"readback", "one_shot_only"}', source)
        self.assertIn('{"xenos_draw", "preserved"}', source)
        self.assertIn('{"draw_suppression", "false"}', source)

    def test_visibility_workset_shadow_replay_is_bounded_and_safe(self) -> None:
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        start = source.index(
            "if (g_visibility_shadow_replay.requested &&\n"
            "      g_visibility_shadow_replay.valid &&"
        )
        end = source.index(
            "if (!g_isolated_draw.requested || !g_isolated_draw.valid ||",
            start,
        )
        request = source[start:end]
        self.assertIn("prepared_visibility_candidate_fresh", request)
        self.assertIn("prepared_title_lod_valid", request)
        self.assertIn("prepared_candidate_eligible", request)
        self.assertIn("last_request_frame", request)
        self.assertIn("request.requested = true", request)
        self.assertIn("request.reference_marker_requested = true", request)
        self.assertIn("CompleteVisibilityShadowReplay", request)
        self.assertNotIn("readback_requested", request)
        self.assertNotIn("publish_to_guest_requested", request)
        self.assertNotIn("suppress_guest_draw", request)
        self.assertIn("requests_without_title_lod", request)

        self.assertIn(
            '"native_renderer.visibility_shadow_replay.summary"', source
        )
        self.assertIn('"selection_accounting_complete"', source)
        self.assertIn('"maximum_draws_per_frame"', source)
        self.assertIn('"optional_exact_metadata_no_inference"', source)
        self.assertIn(
            "g_title_provenance_installed.load(std::memory_order_acquire)",
            source,
        )
        self.assertIn('semantic_lineage_armed ? "armed" : "unavailable"', source)
        self.assertIn('{"readback", "disabled"}', source)
        self.assertIn('{"xenos_draw", "preserved"}', source)
        self.assertIn('{"draw_suppression", "false"}', source)

        capture = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("[switch]$VisibilityShadowReplay", capture)
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_VISIBILITY_SHADOW_REPLAY",
            capture,
        )
        self.assertIn(
            "REX_PINYON_SHIFT_NATIVE_RENDERER_DISPATCH_DISCOVERY",
            capture,
        )
        self.assertIn(
            "VisibilityShadowReplay is mutually exclusive with "
            "isolated/pass replay options.",
            capture,
        )



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
        self.assertEqual(
            analysis.count(
                'name = "PinyonShiftObserveProceduralModelRenderItemExit"'
            ),
            1,
        )
        hook = analysis.split(
            'name = "PinyonShiftObserveProceduralModelRenderItem"', 1
        )[0].rsplit("[[midasm_hook]]", 1)[1]
        self.assertIn("address = 0x8241741C", hook)
        exit_hook = analysis.split(
            'name = "PinyonShiftObserveProceduralModelRenderItemExit"', 1
        )[0].rsplit("[[midasm_hook]]", 1)[1]
        self.assertIn("address = 0x82417B80", exit_hook)
        self.assertIn("kSemanticRenderItemStackCapacity = 32", source)
        self.assertIn("exact_render_item_scope_and_physical_pm4_header", source)
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

    def test_visibility_lod_census_is_exact_bounded_and_passive(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        summarizer = (
            ROOT / "tools/summarize-native-renderer-visibility.py"
        ).read_text(encoding="utf-8")
        hooks = {
            "PinyonShiftObserveProceduralModelVisibilityRecordEntry": (
                "0x82E20094"
            ),
            "PinyonShiftObserveProceduralModelVisibilityLodPrimary": (
                "0x82E205E4"
            ),
            "PinyonShiftObserveProceduralModelVisibilityLodSecondary": (
                "0x82E206DC"
            ),
            "PinyonShiftObserveProceduralModelVisibilityResult": "0x82E206F8",
            "PinyonShiftObserveProceduralModelVisibilityRecordExit": (
                "0x82E2084C"
            ),
            "PinyonShiftObserveProceduralModelVisibilityRuntimeThreshold": (
                "0x82E20134"
            ),
            "PinyonShiftObserveProceduralModelVisibilityDescriptorThreshold": (
                "0x82E201B0"
            ),
            "PinyonShiftObserveProceduralModelVisibilityCandidateThreshold": (
                "0x82E20258"
            ),
            "PinyonShiftObserveProceduralModelVisibilityLocalDistance": (
                "0x82E202D8"
            ),
            "PinyonShiftObserveProceduralModelVisibilitySpatialHelperInput": (
                "0x82E2034C"
            ),
            "PinyonShiftObserveProceduralModelVisibilitySpatialHelperResult": (
                "0x82E20350"
            ),
            "PinyonShiftObserveProceduralModelVisibilityCategoryHelperInput": (
                "0x82E20364"
            ),
            "PinyonShiftObserveProceduralModelVisibilityCategoryHelperResult": (
                "0x82E20368"
            ),
        }
        for name, address in hooks.items():
            self.assertEqual(analysis.count(f'name = "{name}"'), 1)
            hook = analysis.split(f'name = "{name}"', 1)[0].rsplit(
                "[[midasm_hook]]", 1
            )[1]
            self.assertIn(f"address = {address}", hook)
            self.assertNotIn("jump_address", hook)
        self.assertIn("kSemanticVisibilityCategoryCapacity = 32", source)
        self.assertIn("kSemanticVisibilityLodCapacity = 32", source)
        self.assertIn("title_authoritative_visibility_and_lod_observation", source)
        self.assertNotIn("REX_STORE", source)
        self.assertIn('"native_culling": False', summarizer)
        self.assertIn('"native_lod": False', summarizer)
        self.assertIn('"xenos_authority": True', summarizer)
        self.assertIn('"suppression_allowed": False', summarizer)

        policy_summarizer = (
            ROOT / "tools/summarize-native-renderer-visibility-policy.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "kSemanticVisibilitySpatialExponentCapacity = 256", source
        )
        self.assertIn(
            "title_spatial_policy_input_outcome_correlation", source
        )
        self.assertIn(
            '"native_policy_execution_enabled": False', policy_summarizer
        )
        self.assertIn('"xenos_authority": True', policy_summarizer)
        self.assertIn('"suppression_allowed": False', policy_summarizer)

        oracle_summarizer = (
            ROOT / "tools/summarize-native-renderer-visibility-oracle.py"
        ).read_text(encoding="utf-8")
        self.assertIn("title_ordered_visibility_helper_oracle", source)
        self.assertIn('"native_policy_execution_enabled": False', oracle_summarizer)
        self.assertIn('"guest_payload_read": False', oracle_summarizer)
        self.assertIn('"xenos_authority": True', oracle_summarizer)
        self.assertIn('"suppression_allowed": False', oracle_summarizer)

        shadow_summarizer = (
            ROOT / "tools/summarize-native-renderer-visibility-shadow.py"
        ).read_text(encoding="utf-8")
        self.assertIn("title_result_domain_shadow_selection", source)
        self.assertIn('"native_policy_execution": "shadow_only"', shadow_summarizer)
        self.assertIn('"guest_state_changed": False', shadow_summarizer)
        self.assertIn('"xenos_authority": True', shadow_summarizer)
        self.assertIn('"suppression_allowed": False', shadow_summarizer)

        spatial_shadow_summarizer = (
            ROOT / "tools/summarize-native-renderer-visibility-spatial-shadow.py"
        ).read_text(encoding="utf-8")
        self.assertIn("independent_spatial_helper_shadow", source)
        self.assertIn(
            '"guest_payload_read": "bounded_spatial_helper_inputs"',
            spatial_shadow_summarizer,
        )
        self.assertIn('"guest_state_changed": False', spatial_shadow_summarizer)
        self.assertIn('"xenos_authority": True', spatial_shadow_summarizer)
        self.assertIn('"suppression_allowed": False', spatial_shadow_summarizer)

        category_shadow_summarizer = (
            ROOT / "tools/summarize-native-renderer-visibility-category-shadow.py"
        ).read_text(encoding="utf-8")
        self.assertIn("independent_category_helper_shadow", source)
        self.assertIn(
            "kAxisSigns = {1.0f, 1.0f, -1.0f}", source
        )
        self.assertIn('{"axis_signs", "1,1,-1"}', source)
        self.assertIn(
            '"guest_payload_read": "bounded_category_planes"',
            category_shadow_summarizer,
        )
        self.assertIn('"guest_state_changed": False', category_shadow_summarizer)
        self.assertIn('"xenos_authority": True', category_shadow_summarizer)
        self.assertIn('"suppression_allowed": False', category_shadow_summarizer)

        assembly_shadow_summarizer = (
            ROOT
            / "tools/summarize-native-renderer-visibility-assembly-shadow.py"
        ).read_text(encoding="utf-8")
        self.assertIn("independent_visibility_policy_assembly_shadow", source)
        self.assertIn(
            '"guest_payload_read": "bounded_spatial_and_category_inputs"',
            assembly_shadow_summarizer,
        )
        self.assertIn('"guest_state_changed": False', assembly_shadow_summarizer)
        self.assertIn('"xenos_authority": True', assembly_shadow_summarizer)
        self.assertIn('"suppression_allowed": False', assembly_shadow_summarizer)

        workset_summarizer = (
            ROOT / "tools/summarize-native-renderer-visibility-workset.py"
        ).read_text(encoding="utf-8")
        self.assertIn("bounded_host_visibility_workset", source)
        self.assertIn("JoinSemanticVisibilityWorkset", source)
        self.assertIn('"title_culling_changed": False', workset_summarizer)
        self.assertIn('"native_draw": False', workset_summarizer)
        self.assertIn('"xenos_authority": True', workset_summarizer)
        self.assertIn('"suppression_allowed": False', workset_summarizer)

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
            "PinyonShiftObserveProceduralModelResourceProviderLookup": "0x82415B64",
            "PinyonShiftObserveProceduralModelResourceProviderPrimaryPredicate": "0x82415B80",
            "PinyonShiftObserveProceduralModelResourceProviderFallbackPredicate": "0x82415BA4",
            "PinyonShiftObserveProceduralModelResourceProviderMethodResult": "0x82415BC0",
            "PinyonShiftObserveProceduralModelResourceSecondaryResolutionResult": "0x82415BE4",
            "PinyonShiftObserveProceduralModelResourceResolutionResult": "0x82415C50",
            "PinyonShiftObserveProceduralModelResourceBindDispatch": "0x82415C6C",
            "PinyonShiftObserveProceduralModelGeometrySubmission": "0x82417B60",
            "PinyonShiftObserveProceduralModelDirectDrawPacket": "0x82416260",
            "PinyonShiftObserveProceduralModelAlternateDrawPacket": "0x824162F4",
        }
        for name, address in expected_hooks.items():
            self.assertEqual(analysis.count(f'name = "{name}"'), 1)
            hook = analysis.split(f'name = "{name}"', 1)[0].rsplit(
                "[[midasm_hook]]", 1
            )[1]
            self.assertIn(f"address = {address}", hook)
        self.assertIn("kSemanticSubmissionCapacity = 8192", source)
        self.assertIn("kSemanticSubmissionMaximumPayloadBytes = 64", source)
        self.assertIn("runtime_record_24_default", source)
        self.assertIn("runtime_record_28_32", source)
        self.assertIn("resolved_resource_state_variant_and_dispatch_submission", source)
        self.assertIn("graphics_submission_method", source)
        self.assertIn("invalid_dispatch_targets", source)
        self.assertIn("primary_bound_resource_object", source)
        self.assertIn("SemanticResourceProviderProvenance", source)
        self.assertIn("provider_metadata_bytes_per_lookup", source)
        self.assertIn("resource_provider_chain_derivation_proved", summarizer)
        self.assertIn("ProceduralModelHelperStateFamily", source)
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









    def test_census_ledger_tracks_exact_starting_baseline(self):
        ledger = (ROOT / "docs/native-renderer/RENDER_PASS_CENSUS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("cafc7233fef9e039f163d11023f40eccb22e8fc1", ledger)
        self.assertIn("f5337cdc947ff6d4c4196737e2c807a48f2a1fc2", ledger)
        self.assertIn("Unknown work stays on Xenos.", ledger)


if __name__ == "__main__":
    unittest.main()
