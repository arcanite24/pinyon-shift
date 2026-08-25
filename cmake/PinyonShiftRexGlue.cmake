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
    add_subdirectory("${REXSDK_DIR}" rexglue-sdk)
    if(TARGET rexruntime)
        target_compile_definitions(rexruntime PRIVATE REXGLUE_TRACE_IMPORTS=1)
    endif()
    message(STATUS "Using ReXGlue SDK from source tree: ${REXSDK_DIR}")
else()
    if(REXSDK_VERSION)
        find_package(rexglue ${REXSDK_VERSION} EXACT QUIET CONFIG)
    else()
        find_package(rexglue 0.9.0 EXACT QUIET CONFIG)
    endif()
    if(NOT rexglue_FOUND)
        message(FATAL_ERROR
            "ReXGlue SDK 0.9.0 not found. Set REXSDK_DIR to the pinned source tree "
            "or install the exact SDK package.")
    endif()
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

if(NOT EXISTS "${PINYON_SHIFT_GENERATED_DIR}/sources.cmake")
    message(FATAL_ERROR
        "Local generated source is missing. Run the Pinyon Shift launcher or "
        "tools/setup-preview.ps1 with a supported disc image before configuring.")
endif()
include("${PINYON_SHIFT_GENERATED_DIR}/sources.cmake")
set(PINYON_SHIFT_GENERATED_SOURCES ${GENERATED_SOURCES})

function(pinyon_shift_attach_rexglue target_name)
    target_sources(${target_name} PRIVATE ${PINYON_SHIFT_GENERATED_SOURCES})
    target_include_directories(${target_name} PRIVATE
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
    rexglue_configure_target(${target_name} GPU_PLUGINS xenos)
    if(REXSDK_DIR)
        # rex/version.h is configured into the SDK sub-build and is needed only
        # by the injected rex_app.cpp consumer source.
        set_property(SOURCE "${REXGLUE_SHARE_DIR}/rex_app.cpp" APPEND PROPERTY
            INCLUDE_DIRECTORIES "${CMAKE_CURRENT_BINARY_DIR}/rexglue-sdk/include")

        # ReXGlue's target helper copies runtime DLLs only after the host links.
        # An incremental SDK-only relink would therefore leave an older DLL next
        # to an otherwise current host. This target runs on every build (with
        # copy_if_different) and makes the executable's load-time artifact exact.
        add_custom_target(${target_name}_stage_rexruntime ALL
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:rexruntime>
                $<TARGET_FILE_DIR:${target_name}>/$<TARGET_FILE_NAME:rexruntime>
            DEPENDS ${target_name} rexruntime
            COMMENT "Staging the current ReXGlue runtime beside ${target_name}"
            VERBATIM)
    endif()
endfunction()

# The manifest intentionally lives under config/rexglue while generated trees
# are private dependencies under .local. Attach each trace-proven module from
# its resolved repository-local output explicitly instead of including an
# SDK-emitted project-root helper.
function(pinyon_shift_add_generated_module target_name generated_directory)
    set(_generated_dir
        "${PINYON_SHIFT_GENERATED_ROOT}/${generated_directory}")
    if(NOT EXISTS "${_generated_dir}/sources.cmake")
        return()
    endif()

    # include() executes in this function scope, keeping GENERATED_SOURCES from
    # one module from leaking into the next module or the main executable.
    include("${_generated_dir}/sources.cmake")
    add_library(${target_name} SHARED ${GENERATED_SOURCES})
    target_include_directories(${target_name} PRIVATE "${_generated_dir}")
    target_link_libraries(${target_name} PRIVATE rex::runtime)
    set_target_properties(${target_name} PROPERTIES CXX_VISIBILITY_PRESET hidden)
    rexglue_configure_module_target(${target_name} HOST ${REXGLUE_HOST_TARGET})
endfunction()

pinyon_shift_add_generated_module(pinyon_shift_SpeechFacade_default speech)
pinyon_shift_add_generated_module(pinyon_shift_XMediaFacade_default xmedia)

add_custom_target(pinyon_shift_codegen
    COMMAND $<TARGET_FILE:rex::rexglue> codegen "${PINYON_SHIFT_MANIFEST}"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Generating local recompiled code for Pinyon Shift"
    VERBATIM
)
