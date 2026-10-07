# ReXGlue integration adapted for the repository's local/generated split.

set(REXSDK_VERSION "" CACHE STRING "Override the pinned ReXGlue SDK version")
set(REXSDK_DIR "" CACHE PATH "Path to the ReXGlue SDK source tree")
set(PINYON_SHIFT_CPU_BASELINE "sse4.1" CACHE STRING
    "Minimum AMD64 CPU feature baseline used by the host and source-built SDK")
set_property(CACHE PINYON_SHIFT_CPU_BASELINE PROPERTY STRINGS "sse4.1" "fma")

# Tracy opens a network listener in non-Release configurations. Private M3
# qualification uses the structured event log and lightweight counters instead,
# so compile Tracy out to avoid a Firewall permission prompt and its background
# network/profiler footprint.
set(REXGLUE_ENABLE_TRACY OFF CACHE BOOL
    "Disable Tracy networking in Pinyon Shift builds" FORCE)
set(PINYON_SHIFT_CAPTURE_PERFORMANCE ON CACHE BOOL
    "Capture lightweight per-frame performance counters in preview builds")
option(PINYON_SHIFT_TRACE_IMPORTS
    "Record first-use guest import reachability diagnostics" ON)
option(PINYON_SHIFT_FROZEN_CODEGEN
    "Use an existing generated snapshot without invoking the code generator" OFF)
# CI has no game, so no generated code: configure only the SDK runtime and
# the host-side tests and tools, which need neither.
option(PINYON_SHIFT_HOST_TESTS_ONLY
    "Configure only host-side tests and tools, without generated game code" OFF)
option(PINYON_SHIFT_RECOMP_IPO
    "Enable interprocedural optimization for generated game code and host" OFF)
set(PINYON_SHIFT_RECOMP_PGO "OFF" CACHE STRING "Recomp PGO mode: OFF, GENERATE, USE")
set_property(CACHE PINYON_SHIFT_RECOMP_PGO PROPERTY STRINGS OFF GENERATE USE)
set(PINYON_SHIFT_RECOMP_PROFILE "" CACHE FILEPATH "Merged LLVM profile for PGO USE")
if(NOT PINYON_SHIFT_RECOMP_PGO MATCHES "^(OFF|GENERATE|USE)$")
    message(FATAL_ERROR "Invalid recomp PGO mode")
endif()
if(NOT PINYON_SHIFT_RECOMP_PGO STREQUAL "OFF" AND
   NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    message(FATAL_ERROR "Recomp PGO currently requires Clang")
endif()
if(PINYON_SHIFT_RECOMP_PGO STREQUAL "USE" AND
   NOT EXISTS "${PINYON_SHIFT_RECOMP_PROFILE}")
    message(FATAL_ERROR "PGO USE requires an existing merged LLVM profile")
endif()

function(pinyon_shift_apply_recomp_profile target_name)
    if(PINYON_SHIFT_RECOMP_PGO STREQUAL "GENERATE")
        target_compile_options(${target_name} PRIVATE -fprofile-generate -fprofile-update=atomic)
        target_link_options(${target_name} PRIVATE -fprofile-generate)
    elseif(PINYON_SHIFT_RECOMP_PGO STREQUAL "USE")
        target_compile_options(${target_name} PRIVATE "-fprofile-use=${PINYON_SHIFT_RECOMP_PROFILE}")
        target_link_options(${target_name} PRIVATE "-fprofile-use=${PINYON_SHIFT_RECOMP_PROFILE}")
    endif()
endfunction()
if(PINYON_SHIFT_RECOMP_IPO)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT _pinyon_ipo_supported OUTPUT _pinyon_ipo_error LANGUAGES CXX)
    if(NOT _pinyon_ipo_supported)
        message(FATAL_ERROR "Recomp IPO is unavailable: ${_pinyon_ipo_error}")
    endif()
endif()

if(PINYON_SHIFT_CAPTURE_PERFORMANCE)
    # ReXGlue keeps lightweight counters out of Release by default even when
    # their sources are present. Pinyon Shift preview builds need those
    # counters for session CSVs, independently of Tracy's profiler/networking.
    add_compile_definitions(REXGLUE_ENABLE_PERF_COUNTERS)
endif()

if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    if(NOT PINYON_SHIFT_CPU_BASELINE MATCHES "^(sse4\\.1|fma)$")
        message(FATAL_ERROR
            "Pinyon Shift supports the audited SSE4.1 AMD64 baseline and its FMA3 "
            "variant (PINYON_SHIFT_CPU_BASELINE sse4.1 or fma)")
    endif()
    if(NOT CMAKE_C_FLAGS MATCHES "(^| )-msse4\\.1($| )" OR
       NOT CMAKE_CXX_FLAGS MATCHES "(^| )-msse4\\.1($| )")
        message(FATAL_ERROR
            "The AMD64 source build must explicitly compile C and C++ with "
            "-msse4.1; use the checked-in CMake presets")
    endif()
    # NP-3.5: the FMA3 baseline lowers the std::fma the generated code uses for
    # the Xenon's fused multiply-adds to one instruction instead of a CRT call;
    # the result is bit-identical. Contraction stays off so no separate
    # multiply and add is ever fused, which would change results.
    if(PINYON_SHIFT_CPU_BASELINE STREQUAL "fma")
        foreach(_flags IN ITEMS CMAKE_C_FLAGS CMAKE_CXX_FLAGS)
            if(NOT ${_flags} MATCHES "(^| )-mfma($| )" OR
               NOT ${_flags} MATCHES "(^| )-ffp-contract=off($| )")
                message(FATAL_ERROR
                    "The fma baseline must compile with -msse4.1 -mfma -ffp-contract=off")
            endif()
        endforeach()
        add_compile_definitions(PINYON_SHIFT_CPU_BASELINE_FMA=1)
    elseif(CMAKE_C_FLAGS MATCHES "(^| )-mfma($| )" OR CMAKE_CXX_FLAGS MATCHES "(^| )-mfma($| )")
        message(FATAL_ERROR "-mfma needs PINYON_SHIFT_CPU_BASELINE=fma")
    endif()
    if(WIN32 AND CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        # LLD otherwise writes the wall clock into each PE/COFF image. Combined
        # with the wrapper's locked SOURCE_DATE_EPOCH, /Brepro makes identical
        # source and generated trees produce byte-identical linked artifacts.
        add_link_options("LINKER:/Brepro")
    endif()
endif()

if(REXSDK_DIR)
    # Keep the consumer build's runtime, GPU plugin, and tools inside its own
    # binary tree. ReXGlue's standalone source build retains its pinned out/
    # artifacts and cannot be overwritten by a host relink.
    set(REXGLUE_OUTPUT_DIRECTORY
        "${CMAKE_CURRENT_BINARY_DIR}/rexglue-artifacts"
        CACHE PATH "ReXGlue artifacts for the Pinyon Shift host build" FORCE)
    add_subdirectory("${REXSDK_DIR}" rexglue-sdk EXCLUDE_FROM_ALL)
    # The generator runs on the build host, from the SDK's standalone build
    # for that host (out/<os>-<arch>/Release).
    if(CMAKE_HOST_WIN32)
        set(_codegen_os win)
    elseif(CMAKE_HOST_APPLE)
        set(_codegen_os mac)
    else()
        set(_codegen_os linux)
    endif()
    if(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
        set(_codegen_arch amd64)
    else()
        set(_codegen_arch arm64)
    endif()
    set(PINYON_SHIFT_REXGLUE_CODEGEN
        "${REXSDK_DIR}/out/${_codegen_os}-${_codegen_arch}/Release/rexglue${CMAKE_HOST_EXECUTABLE_SUFFIX}"
        CACHE FILEPATH "The standalone ReXGlue generator")
    if(NOT EXISTS "${PINYON_SHIFT_REXGLUE_CODEGEN}" AND NOT PINYON_SHIFT_HOST_TESTS_ONLY)
        message(FATAL_ERROR
            "The standalone ReXGlue generator is missing. Run tools/build-preview.ps1 "
            "so it can build the pinned generator before configuring the consumer.")
    endif()
    set(PINYON_SHIFT_REXGLUE_CODEGEN_DEPENDS
        "${PINYON_SHIFT_REXGLUE_CODEGEN}")
    if(TARGET rexruntime AND PINYON_SHIFT_TRACE_IMPORTS)
        target_compile_definitions(rexruntime PRIVATE REXGLUE_TRACE_IMPORTS=1)
    endif()
    message(STATUS "Using ReXGlue SDK from source tree: ${REXSDK_DIR}")
else()
    if(REXSDK_VERSION)
        find_package(rexglue ${REXSDK_VERSION} EXACT QUIET CONFIG)
    else()
        find_package(rexglue 0.10.0 EXACT QUIET CONFIG)
    endif()
    if(NOT rexglue_FOUND)
        message(FATAL_ERROR
            "ReXGlue SDK 0.10.0 not found. Set REXSDK_DIR to the pinned source tree "
            "or install the exact SDK package.")
    endif()
    set(PINYON_SHIFT_REXGLUE_CODEGEN $<TARGET_FILE:rex::rexglue>)
    set(PINYON_SHIFT_REXGLUE_CODEGEN_DEPENDS rexglue)
endif()

# TITLE_UPDATE_V4_BACKLOG: build the FH1 v4 title update from the USA disc.
# Its code is generated from the patched executables in a separate tree.
option(PINYON_SHIFT_TITLE_UPDATE_V4
    "Build the FH1 v4 title-update executable (separate generated tree)" OFF)
set(PINYON_SHIFT_CODEGEN_EXTRA_ARGS)
if(PINYON_SHIFT_TITLE_UPDATE_V4)
    set(_pinyon_default_manifest "config/rexglue/pinyon_shift_v4_manifest.toml")
    set(_pinyon_default_generated ".local/generated-v4")
    add_compile_definitions(PINYON_SHIFT_TITLE_UPDATE_V4=1)
    list(APPEND PINYON_SHIFT_CODEGEN_EXTRA_ARGS --xex_apply_patches=true)
    set(_pinyon_codegen_log_suffix "-v4")
else()
    set(_pinyon_codegen_log_suffix "")
    set(_pinyon_default_manifest "config/rexglue/pinyon_shift_manifest.toml")
    set(_pinyon_default_generated ".local/generated")
endif()
set(PINYON_SHIFT_MANIFEST
    "${CMAKE_CURRENT_SOURCE_DIR}/${_pinyon_default_manifest}"
    CACHE FILEPATH "ReXGlue manifest used by the codegen convenience target")
set(PINYON_SHIFT_GENERATED_ROOT
    "${CMAKE_CURRENT_SOURCE_DIR}/${_pinyon_default_generated}"
    CACHE PATH "Root containing the user-local generated main and module trees")
set(PINYON_SHIFT_GENERATED_DIR
    "${PINYON_SHIFT_GENERATED_ROOT}/default"
    CACHE PATH "Generated main-XEX source tree")
set(REXGLUE_HOST_TARGET pinyon_shift)
set(PINYON_SHIFT_CODEGEN_LOG
    "${CMAKE_CURRENT_SOURCE_DIR}/.local/logs/codegen${_pinyon_codegen_log_suffix}.log"
    CACHE FILEPATH "ReXGlue code-generation log")

if(NOT PINYON_SHIFT_HOST_TESTS_ONLY)
if(NOT EXISTS "${PINYON_SHIFT_GENERATED_DIR}/sources.cmake")
    message(FATAL_ERROR
        "Local generated source is missing. Run the Pinyon Shift launcher or "
        "tools/setup-preview.ps1 with a supported disc image before configuring.")
endif()
include("${PINYON_SHIFT_GENERATED_DIR}/sources.cmake")
set(PINYON_SHIFT_GENERATED_SOURCES ${GENERATED_SOURCES})
# Runtime::Setup registers the entrypoint image through PPCFuncMappings.
# Only facade DLLs need the separate generated registration entry point.
list(FILTER PINYON_SHIFT_GENERATED_SOURCES EXCLUDE REGEX "/pinyon_shift_register\\.cpp$")

foreach(_module IN ITEMS speech xmedia)
    set(_module_dir "${PINYON_SHIFT_GENERATED_ROOT}/${_module}")
    if(NOT EXISTS "${_module_dir}/sources.cmake")
        message(FATAL_ERROR
            "Local generated ${_module} source is missing. Run "
            "tools/build-preview.ps1 -CleanGenerated.")
    endif()
    include("${_module_dir}/sources.cmake")
    string(TOUPPER "${_module}" _module_upper)
    set(PINYON_SHIFT_${_module_upper}_GENERATED_SOURCES ${GENERATED_SOURCES})
endforeach()
unset(GENERATED_SOURCES)

# Match the 0.10 generated integration contract. Generated guest code uses
# Windows SEH scopes and therefore must compile with asynchronous exceptions;
# the option must also be present while each target's PCH is built.
set(REXGLUE_RECOMP_DEBUG_INFO "line-tables-only" CACHE STRING
    "Debug info level for generated code: line-tables-only, full, or none")
set(REXGLUE_RECOMP_OPTIONS "")
if(WIN32)
    if(MSVC)
        list(APPEND REXGLUE_RECOMP_OPTIONS /EHa)
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        list(APPEND REXGLUE_RECOMP_OPTIONS -fasync-exceptions)
    endif()
endif()
if(REXGLUE_RECOMP_DEBUG_INFO STREQUAL "none")
    list(APPEND REXGLUE_RECOMP_OPTIONS
        $<$<CXX_COMPILER_ID:Clang,AppleClang,GNU>:-g0>)
elseif(REXGLUE_RECOMP_DEBUG_INFO STREQUAL "line-tables-only")
    list(APPEND REXGLUE_RECOMP_OPTIONS
        $<$<CXX_COMPILER_ID:Clang,AppleClang>:-gline-tables-only>)
endif()

set(_all_generated_sources
    ${PINYON_SHIFT_GENERATED_SOURCES}
    ${PINYON_SHIFT_SPEECH_GENERATED_SOURCES}
    ${PINYON_SHIFT_XMEDIA_GENERATED_SOURCES})
set_source_files_properties(${_all_generated_sources}
    PROPERTIES COMPILE_OPTIONS "${REXGLUE_RECOMP_OPTIONS}")
set(_all_generated_headers)
foreach(_generated_dir IN ITEMS default speech xmedia)
    foreach(_header IN ITEMS pinyon_shift_pch.h pinyon_shift_init.h pinyon_shift_funcs.h)
        list(APPEND _all_generated_headers
            "${PINYON_SHIFT_GENERATED_ROOT}/${_generated_dir}/${_header}")
    endforeach()
endforeach()

function(pinyon_shift_apply_recomp_settings target_name generated_directory)
    target_precompile_headers(${target_name} PRIVATE
        "${generated_directory}/pinyon_shift_pch.h")
    target_compile_options(${target_name} PRIVATE ${REXGLUE_RECOMP_OPTIONS})
endfunction()

# The entrypoint stamp's depfile records the manifest, included analysis TOMLs,
# all three game binaries, and the SDK version. The generator writes the stamp
# only after every entrypoint/module output succeeds.
if(NOT PINYON_SHIFT_FROZEN_CODEGEN)
add_custom_command(
    OUTPUT "${PINYON_SHIFT_GENERATED_DIR}/codegen.build.stamp"
    # The headers every unit includes are outputs too: Ninja reads the state
    # of a file no edge produces once, before the generator runs, so a header
    # it rewrote would otherwise leave the precompiled headers stale.
    BYPRODUCTS
        "${PINYON_SHIFT_GENERATED_DIR}/codegen.d"
        ${_all_generated_sources}
        ${_all_generated_headers}
    COMMAND ${CMAKE_COMMAND} -E make_directory
        "${CMAKE_CURRENT_SOURCE_DIR}/.local/logs"
    COMMAND "${PINYON_SHIFT_REXGLUE_CODEGEN}"
        --log-level info
        --log-file "${PINYON_SHIFT_CODEGEN_LOG}"
        codegen "${PINYON_SHIFT_MANIFEST}" --ignore-stamp ${PINYON_SHIFT_CODEGEN_EXTRA_ARGS}
    DEPENDS ${PINYON_SHIFT_REXGLUE_CODEGEN_DEPENDS} "${PINYON_SHIFT_MANIFEST}"
    DEPFILE "${PINYON_SHIFT_GENERATED_DIR}/codegen.d"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Generating dependency-tracked recompiled code for Pinyon Shift"
    VERBATIM)
add_custom_target(pinyon_shift_codegen
    DEPENDS "${PINYON_SHIFT_GENERATED_DIR}/codegen.build.stamp")
else()
    if(NOT EXISTS "${PINYON_SHIFT_GENERATED_DIR}/codegen.build.stamp")
        message(FATAL_ERROR "Frozen codegen requires a complete generated snapshot")
    endif()
    add_custom_target(pinyon_shift_codegen)
endif()
endif()  # NOT PINYON_SHIFT_HOST_TESTS_ONLY

set(PINYON_SHIFT_STAGE_FILE_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/PinyonStageFile.cmake")

function(pinyon_shift_attach_rexglue target_name)
    if(PINYON_SHIFT_RECOMP_PGO STREQUAL "GENERATE")
        target_compile_definitions(${target_name} PRIVATE PINYON_SHIFT_PGO_GENERATE=1)
    endif()
    add_library(${target_name}_recomp OBJECT ${PINYON_SHIFT_GENERATED_SOURCES})
    pinyon_shift_apply_recomp_profile(${target_name}_recomp)
    pinyon_shift_apply_recomp_profile(${target_name})
    if(PINYON_SHIFT_RECOMP_IPO)
        set_property(TARGET ${target_name}_recomp ${target_name}
            PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
    endif()
    target_include_directories(${target_name}_recomp PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}"
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${PINYON_SHIFT_GENERATED_DIR}")
    target_link_libraries(${target_name}_recomp PRIVATE rex::runtime)
    rexglue_apply_target_settings(${target_name}_recomp)
    pinyon_shift_apply_recomp_settings(
        ${target_name}_recomp "${PINYON_SHIFT_GENERATED_DIR}")
    add_dependencies(${target_name}_recomp pinyon_shift_codegen)
    target_link_libraries(${target_name} PRIVATE ${target_name}_recomp)

    target_include_directories(${target_name} PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}"
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${PINYON_SHIFT_GENERATED_DIR}"
    )
    # The source-tree helper injects rex_app.cpp into the consumer, while imgui
    # remains a private SDK dependency. Keep its include local to source builds.
    if(REXSDK_DIR)
        target_include_directories(${target_name} PRIVATE
            "${REXSDK_DIR}/thirdparty/imgui")
    endif()
    target_link_libraries(${target_name} PRIVATE rex::runtime)
    target_compile_definitions(${target_name} PRIVATE
        PINYON_SHIFT_CPU_BASELINE="${PINYON_SHIFT_CPU_BASELINE}")
    add_dependencies(${target_name} pinyon_shift_codegen)
    rexglue_configure_target(${target_name} GPU_PLUGINS fh1)
    if(REXSDK_DIR)
        # rex/version.h is configured into the SDK sub-build and is needed only
        # by the injected rex_app.cpp consumer source.
        set_property(SOURCE "${REXGLUE_SHARE_DIR}/rex_app.cpp" APPEND PROPERTY
            INCLUDE_DIRECTORIES "${CMAKE_CURRENT_BINARY_DIR}/rexglue-sdk/include")

        # ReXGlue's target helper copies runtime DLLs only after the host links.
        # An incremental SDK-only relink would therefore leave older runtime or
        # graphics backend DLLs next to an otherwise current host. This target
        # runs on every build (copying only changed files) and makes the
        # executable's load-time artifacts exact. PinyonStageFile.cmake retries
        # while antivirus briefly holds a fresh DLL and otherwise names the
        # locked file and the fix instead of a bare "Error copying file".
        add_custom_target(${target_name}_stage_rexruntime ALL
            COMMAND ${CMAKE_COMMAND}
                -DSOURCE=$<TARGET_FILE:rexruntime>
                -DDESTINATION=$<TARGET_FILE_DIR:${target_name}>/$<TARGET_FILE_NAME:rexruntime>
                -P ${PINYON_SHIFT_STAGE_FILE_SCRIPT}
            COMMAND ${CMAKE_COMMAND}
                -DSOURCE=$<TARGET_FILE:rexgpu-fh1>
                -DDESTINATION=$<TARGET_FILE_DIR:${target_name}>/$<TARGET_FILE_NAME:rexgpu-fh1>
                -P ${PINYON_SHIFT_STAGE_FILE_SCRIPT}
            DEPENDS ${target_name} rexruntime rexgpu-fh1
            COMMENT "Staging the current ReXGlue runtime and graphics backend beside ${target_name}"
            VERBATIM)
    endif()
endfunction()

# The manifest intentionally lives under config/rexglue while generated trees
# are private dependencies under .local. Attach each trace-proven module from
# its resolved repository-local output explicitly instead of including an
# SDK-emitted project-root helper.
function(pinyon_shift_add_generated_module target_name generated_directory generated_sources)
    set(_generated_dir
        "${PINYON_SHIFT_GENERATED_ROOT}/${generated_directory}")
    add_library(${target_name} SHARED ${generated_sources})
    pinyon_shift_apply_recomp_profile(${target_name})
    if(PINYON_SHIFT_RECOMP_IPO)
        set_property(TARGET ${target_name} PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
    endif()
    target_include_directories(${target_name} PRIVATE "${_generated_dir}")
    target_link_libraries(${target_name} PRIVATE rex::runtime)
    pinyon_shift_apply_recomp_settings(${target_name} "${_generated_dir}")
    add_dependencies(${target_name} pinyon_shift_codegen)
    set_target_properties(${target_name} PROPERTIES CXX_VISIBILITY_PRESET hidden)
    rexglue_configure_module_target(${target_name} HOST ${REXGLUE_HOST_TARGET})
endfunction()

if(NOT PINYON_SHIFT_HOST_TESTS_ONLY)
    pinyon_shift_add_generated_module(
        pinyon_shift_SpeechFacade_default speech
        "${PINYON_SHIFT_SPEECH_GENERATED_SOURCES}")
    pinyon_shift_add_generated_module(
        pinyon_shift_XMediaFacade_default xmedia
        "${PINYON_SHIFT_XMEDIA_GENERATED_SOURCES}")
endif()
