# ReXGlue integration adapted for the repository's local/generated split.

set(REXSDK_VERSION "" CACHE STRING "Override the pinned ReXGlue SDK version")
set(REXSDK_DIR "" CACHE PATH "Path to the ReXGlue SDK source tree")
set(PINYON_SHIFT_CPU_BASELINE "sse4.1" CACHE STRING
    "Minimum AMD64 CPU feature baseline used by the host and source-built SDK")
set_property(CACHE PINYON_SHIFT_CPU_BASELINE PROPERTY STRINGS "sse4.1")

# Tracy opens a network listener in non-Release configurations. Private M3
# qualification uses the structured event log and lightweight counters instead,
# so compile Tracy out to avoid a Firewall permission prompt and its background
# network/profiler footprint.
set(REXGLUE_ENABLE_TRACY OFF CACHE BOOL
    "Disable Tracy networking in Pinyon Shift builds" FORCE)
set(PINYON_SHIFT_CAPTURE_PERFORMANCE ON CACHE BOOL
    "Capture lightweight per-frame performance counters in preview builds")

if(PINYON_SHIFT_CAPTURE_PERFORMANCE)
    # ReXGlue keeps lightweight counters out of Release by default even when
    # their sources are present. Pinyon Shift preview builds need those
    # counters for session CSVs, independently of Tracy's profiler/networking.
    add_compile_definitions(REXGLUE_ENABLE_PERF_COUNTERS)
endif()

if(WIN32 AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    if(NOT PINYON_SHIFT_CPU_BASELINE STREQUAL "sse4.1")
        message(FATAL_ERROR
            "Pinyon Shift currently supports only the audited SSE4.1 AMD64 baseline")
    endif()
    if(NOT CMAKE_C_FLAGS MATCHES "(^| )-msse4\\.1($| )" OR
       NOT CMAKE_CXX_FLAGS MATCHES "(^| )-msse4\\.1($| )")
        message(FATAL_ERROR
            "The Windows AMD64 source build must explicitly compile C and C++ "
            "with -msse4.1; use the checked-in CMake presets")
    endif()
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
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
    set(PINYON_SHIFT_REXGLUE_CODEGEN
        "${REXSDK_DIR}/out/win-amd64/Release/rexglue.exe")
    if(NOT EXISTS "${PINYON_SHIFT_REXGLUE_CODEGEN}")
        message(FATAL_ERROR
            "The standalone ReXGlue generator is missing. Run tools/build-preview.ps1 "
            "so it can build the pinned generator before configuring the consumer.")
    endif()
    set(PINYON_SHIFT_REXGLUE_CODEGEN_DEPENDS
        "${PINYON_SHIFT_REXGLUE_CODEGEN}")
    if(TARGET rexruntime)
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

set(PINYON_SHIFT_MANIFEST
    "${CMAKE_CURRENT_SOURCE_DIR}/config/rexglue/pinyon_shift_manifest.toml"
    CACHE FILEPATH "ReXGlue manifest used by the codegen convenience target")
set(PINYON_SHIFT_GENERATED_ROOT
    "${CMAKE_CURRENT_SOURCE_DIR}/.local/generated"
    CACHE PATH "Root containing the user-local generated main and module trees")
set(PINYON_SHIFT_GENERATED_DIR
    "${PINYON_SHIFT_GENERATED_ROOT}/default"
    CACHE PATH "Generated main-XEX source tree")
set(REXGLUE_HOST_TARGET pinyon_shift)
set(PINYON_SHIFT_CODEGEN_LOG
    "${CMAKE_CURRENT_SOURCE_DIR}/.local/logs/codegen.log"
    CACHE FILEPATH "ReXGlue code-generation log")

if(NOT EXISTS "${PINYON_SHIFT_GENERATED_DIR}/sources.cmake")
    message(FATAL_ERROR
        "Local generated source is missing. Run the Pinyon Shift launcher or "
        "tools/setup-preview.ps1 with a supported disc image before configuring.")
endif()
include("${PINYON_SHIFT_GENERATED_DIR}/sources.cmake")
set(PINYON_SHIFT_GENERATED_SOURCES ${GENERATED_SOURCES})

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

function(pinyon_shift_apply_recomp_settings target_name generated_directory)
    target_precompile_headers(${target_name} PRIVATE
        "${generated_directory}/pinyon_shift_pch.h")
    target_compile_options(${target_name} PRIVATE ${REXGLUE_RECOMP_OPTIONS})
endfunction()

# The entrypoint stamp's depfile records the manifest, included analysis TOMLs,
# all three game binaries, and the SDK version. The generator writes the stamp
# only after every entrypoint/module output succeeds.
add_custom_command(
    OUTPUT "${PINYON_SHIFT_GENERATED_DIR}/codegen.build.stamp"
    BYPRODUCTS
        "${PINYON_SHIFT_GENERATED_DIR}/codegen.d"
        ${_all_generated_sources}
    COMMAND ${CMAKE_COMMAND} -E make_directory
        "${CMAKE_CURRENT_SOURCE_DIR}/.local/logs"
    COMMAND "${PINYON_SHIFT_REXGLUE_CODEGEN}"
        --log-level info
        --log-file "${PINYON_SHIFT_CODEGEN_LOG}"
        codegen "${PINYON_SHIFT_MANIFEST}" --ignore-stamp
    DEPENDS ${PINYON_SHIFT_REXGLUE_CODEGEN_DEPENDS} "${PINYON_SHIFT_MANIFEST}"
    DEPFILE "${PINYON_SHIFT_GENERATED_DIR}/codegen.d"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Generating dependency-tracked recompiled code for Pinyon Shift"
    VERBATIM)
add_custom_target(pinyon_shift_codegen
    DEPENDS "${PINYON_SHIFT_GENERATED_DIR}/codegen.build.stamp")

function(pinyon_shift_attach_rexglue target_name)
    add_library(${target_name}_recomp OBJECT ${PINYON_SHIFT_GENERATED_SOURCES})
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
    rexglue_configure_target(${target_name} GPU_PLUGINS xenos)
    if(REXSDK_DIR)
        # rex/version.h is configured into the SDK sub-build and is needed only
        # by the injected rex_app.cpp consumer source.
        set_property(SOURCE "${REXGLUE_SHARE_DIR}/rex_app.cpp" APPEND PROPERTY
            INCLUDE_DIRECTORIES "${CMAKE_CURRENT_BINARY_DIR}/rexglue-sdk/include")

        # ReXGlue's target helper copies runtime DLLs only after the host links.
        # An incremental SDK-only relink would therefore leave older runtime or
        # graphics backend DLLs next to an otherwise current host. This target
        # runs on every build (with copy_if_different) and makes the executable's
        # load-time artifacts exact.
        add_custom_target(${target_name}_stage_rexruntime ALL
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:rexruntime>
                $<TARGET_FILE_DIR:${target_name}>/$<TARGET_FILE_NAME:rexruntime>
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:rexgpu-xenos>
                $<TARGET_FILE_DIR:${target_name}>/$<TARGET_FILE_NAME:rexgpu-xenos>
            DEPENDS ${target_name} rexruntime rexgpu-xenos
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
    target_include_directories(${target_name} PRIVATE "${_generated_dir}")
    target_link_libraries(${target_name} PRIVATE rex::runtime)
    pinyon_shift_apply_recomp_settings(${target_name} "${_generated_dir}")
    add_dependencies(${target_name} pinyon_shift_codegen)
    set_target_properties(${target_name} PROPERTIES CXX_VISIBILITY_PRESET hidden)
    rexglue_configure_module_target(${target_name} HOST ${REXGLUE_HOST_TARGET})
endfunction()

pinyon_shift_add_generated_module(
    pinyon_shift_SpeechFacade_default speech
    "${PINYON_SHIFT_SPEECH_GENERATED_SOURCES}")
pinyon_shift_add_generated_module(
    pinyon_shift_XMediaFacade_default xmedia
    "${PINYON_SHIFT_XMEDIA_GENERATED_SOURCES}")
