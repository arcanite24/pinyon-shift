# Pinyon Shift - native ReXGlue host

cmake_minimum_required(VERSION 3.25)
project(pinyon_shift LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# SDL uses native Windows HID and XInput backends here. Its optional libusb
# probe is for platforms/controllers that need direct USB access and should not
# make a normal Windows build look like it has a missing dependency.
if(ANDROID)
    # Every library in the package is position independent, the generated
    # code's object library included.
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()
if(WIN32)
    set(SDL_HIDAPI_LIBUSB OFF CACHE BOOL "Disable optional libusb HID backend on Windows" FORCE)
endif()

include(cmake/PinyonShiftRexGlue.cmake)

set(PINYON_SHIFT_HOST_SOURCES
    src/main.cpp
    src/cpu_baseline_guard.cpp
    src/fh1_render_test.cpp
    src/pinyon_shift_app.cpp
    src/pinyon_shift_diagnostics.cpp
    src/pinyon_shift_runtime_hooks.cpp
    src/save_backups.cpp
    src/cheats.cpp
    src/cheats_map.cpp
    src/dlc_token_unlocks.cpp
    src/dlc_treasure_map.cpp
    src/dlc/rally_progress.cpp
    src/dlc/rally_pace_notes.cpp
    src/dlc/rally_audio_probe.cpp
    src/stall_dump.cpp
    src/save/car_cards.cpp
    src/save/live_profile.cpp
    src/save/profile_body.cpp
    src/mod/mod_host.cpp
    src/mod/overlay_device.cpp
    src/ui/fh1_ui_api.cpp
    src/ui/ui_strings.cpp
    src/ui/host_style.cpp
    src/ui/hostui/fh1_archive.cpp
    src/ui/hostui/glyph_atlas.cpp
    src/ui/hostui/host_ui.cpp
    src/ui/hostui/menu.cpp
    src/ui/hostui/vector_font.cpp
    src/ui/hostui/xds_texture.cpp
    src/ui/settings_menu.cpp
    src/ui/photo_export.cpp
    src/ui/png_writer.cpp
    src/ui/xam_dialogs.cpp
    src/ui/achievements_menu.cpp
    src/ui/touch_pad.cpp
    src/config/host_config.cpp
    src/platform/host_platform.cpp
    src/platform/sha256.cpp
    ${REXSDK_DIR}/thirdparty/crypto/sha256.cpp
    src/native_renderer/graphics_hooks.cpp
    src/native_renderer/guest_output_renderer.cpp
    src/native_renderer/shader_capture.cpp
)

if(PINYON_SHIFT_HOST_TESTS_ONLY)
    # No game target; the tests and tools below still build.
elseif(WIN32)
    add_executable(pinyon_shift WIN32
        ${PINYON_SHIFT_HOST_SOURCES}
        src/crash_reporter_win.cpp
    )
elseif(ANDROID)
    # SDL's activity loads the game as libmain.so and calls its SDL_main; the
    # runtime, the GPU plugin and the facades are libraries beside it.
    add_library(pinyon_shift SHARED
        ${PINYON_SHIFT_HOST_SOURCES}
        src/crash_reporter_posix.cpp
    )
    set_target_properties(pinyon_shift PROPERTIES OUTPUT_NAME main)
else()
    add_executable(pinyon_shift
        ${PINYON_SHIFT_HOST_SOURCES}
        src/crash_reporter_posix.cpp
    )
endif()

add_executable(pinyon_shift_fh1_ui_api_tests EXCLUDE_FROM_ALL
    tests/ui/fh1_ui_api_test.cpp
    src/ui/fh1_ui_api.cpp
)
target_include_directories(pinyon_shift_fh1_ui_api_tests PRIVATE src)

add_executable(pinyon_shift_fh1_shader_pack_tests EXCLUDE_FROM_ALL
    tests/native_renderer/fh1_shader_pack_test.cpp
    ${REXSDK_DIR}/src/graphics/fh1_shader_pack.cpp
)
# The SDK root too: off Windows the pack hashes with its bundled SHA-256.
target_include_directories(pinyon_shift_fh1_shader_pack_tests PRIVATE
    ${REXSDK_DIR}/include ${REXSDK_DIR})
target_link_libraries(pinyon_shift_fh1_shader_pack_tests PRIVATE rex::runtime)
if(WIN32)
    target_link_libraries(pinyon_shift_fh1_shader_pack_tests PRIVATE bcrypt)
endif()

add_executable(pinyon_shift_hostui_tests EXCLUDE_FROM_ALL
    tests/ui/hostui_test.cpp
    src/ui/hostui/fh1_archive.cpp
    src/ui/hostui/glyph_atlas.cpp
    src/ui/hostui/menu.cpp
    src/ui/hostui/vector_font.cpp
    src/ui/hostui/xds_texture.cpp
)
target_include_directories(pinyon_shift_hostui_tests PRIVATE src ${REXSDK_DIR}/include)
target_link_libraries(pinyon_shift_hostui_tests PRIVATE rex::runtime)

add_executable(pinyon_shift_host_config_tests EXCLUDE_FROM_ALL
    tests/config/host_config_test.cpp
    src/config/host_config.cpp
    src/platform/host_platform.cpp
)
target_include_directories(pinyon_shift_host_config_tests PRIVATE src)

add_executable(pinyon_shift_profile_body_tests EXCLUDE_FROM_ALL
    tests/save/profile_body_test.cpp
    src/save/profile_body.cpp
)
target_include_directories(pinyon_shift_profile_body_tests PRIVATE src)

add_executable(pinyon_shift_rally_progress_tests EXCLUDE_FROM_ALL
    tests/dlc/rally_progress_test.cpp
    src/dlc/rally_progress.cpp src/platform/host_platform.cpp)
target_include_directories(pinyon_shift_rally_progress_tests PRIVATE src)
target_include_directories(pinyon_shift_rally_progress_tests SYSTEM PRIVATE
    ${REXSDK_DIR}/thirdparty/tomlplusplus/include)

add_executable(pinyon_shift_rally_pace_tests EXCLUDE_FROM_ALL
    tests/dlc/rally_pace_notes_test.cpp src/dlc/rally_pace_notes.cpp)
target_include_directories(pinyon_shift_rally_pace_tests PRIVATE src)
target_include_directories(pinyon_shift_rally_pace_tests SYSTEM PRIVATE
    ${REXSDK_DIR}/thirdparty/tomlplusplus/include)

add_executable(pinyon_shift_car_cards_tests EXCLUDE_FROM_ALL
    tests/save/car_cards_test.cpp
    src/save/car_cards.cpp
)
target_include_directories(pinyon_shift_car_cards_tests PRIVATE src)
target_link_libraries(pinyon_shift_car_cards_tests PRIVATE rex::runtime)

add_executable(pinyon_shift_save_backups_tests EXCLUDE_FROM_ALL
    tests/save/save_backups_test.cpp src/save_backups.cpp)
target_include_directories(pinyon_shift_save_backups_tests PRIVATE src)
target_link_libraries(pinyon_shift_save_backups_tests PRIVATE rex::runtime)

add_executable(pinyon_shift_content_roots_tests EXCLUDE_FROM_ALL
    tests/dlc/content_roots_test.cpp)
target_link_libraries(pinyon_shift_content_roots_tests PRIVATE rex::runtime)

add_executable(pinyon_shift_fh1_edram_tiles_tests EXCLUDE_FROM_ALL
    tests/native_renderer/fh1_edram_tiles_test.cpp
)
target_include_directories(pinyon_shift_fh1_edram_tiles_tests PRIVATE ${REXSDK_DIR}/include)
target_link_libraries(pinyon_shift_fh1_edram_tiles_tests PRIVATE rex::runtime)

add_executable(pinyon_shift_overlay_device_tests EXCLUDE_FROM_ALL
    tests/mod/overlay_device_test.cpp src/mod/overlay_device.cpp)
target_include_directories(pinyon_shift_overlay_device_tests PRIVATE src)
target_link_libraries(pinyon_shift_overlay_device_tests PRIVATE rex::runtime)

# Every host-side test, for CI (PINYON_SHIFT_HOST_TESTS_ONLY) and local runs.
add_custom_target(pinyon_shift_host_tests)
add_dependencies(pinyon_shift_host_tests
    pinyon_shift_fh1_ui_api_tests
    pinyon_shift_fh1_shader_pack_tests
    pinyon_shift_hostui_tests
    pinyon_shift_host_config_tests
    pinyon_shift_profile_body_tests
    pinyon_shift_rally_progress_tests
    pinyon_shift_rally_pace_tests
    pinyon_shift_car_cards_tests
    pinyon_shift_save_backups_tests
    pinyon_shift_content_roots_tests
    pinyon_shift_overlay_device_tests
    pinyon_shift_fh1_edram_tiles_tests
    pinyon_shift_mod_hello_telemetry)

# These checks use assert; Release must execute them instead of compiling
# away the test operations themselves.
get_target_property(pinyon_host_checks pinyon_shift_host_tests MANUALLY_ADDED_DEPENDENCIES)
foreach(pinyon_host_check IN LISTS pinyon_host_checks)
    if(pinyon_host_check MATCHES "_tests$")
        target_compile_options(${pinyon_host_check} PRIVATE
            $<IF:$<CXX_COMPILER_ID:MSVC>,/UNDEBUG,-UNDEBUG>)
    endif()
endforeach()

add_executable(pinyon_shift_fh1_archive_extract EXCLUDE_FROM_ALL
    tools/fh1_archive_extract.cpp
    src/ui/hostui/fh1_archive.cpp
)

add_executable(pinyon_shift_fh1_texture_import EXCLUDE_FROM_ALL
    tools/fh1_texture_import.cpp
    ${REXSDK_DIR}/src/graphics/pipeline/texture/util.cpp
    ${REXSDK_DIR}/src/graphics/pipeline/texture/info_formats.cpp)
target_include_directories(pinyon_shift_fh1_texture_import PRIVATE
    ${REXSDK_DIR}/include)
if(WIN32)
    target_sources(pinyon_shift_fh1_texture_import PRIVATE
        ${REXSDK_DIR}/src/core/math_msvc.cpp)
else()
    target_sources(pinyon_shift_fh1_texture_import PRIVATE
        ${REXSDK_DIR}/src/core/math_gcc.cpp)
endif()
target_include_directories(pinyon_shift_fh1_archive_extract PRIVATE
    src ${REXSDK_DIR}/include)
target_link_libraries(pinyon_shift_fh1_archive_extract PRIVATE rex::runtime)
if(WIN32)
    # Non-elevated sampling profiler for named threads (CPU_HOTSPOT_PROFILING.md).
    add_executable(pinyon_shift_thread_sampler EXCLUDE_FROM_ALL tools/thread_sampler.cpp)
    target_link_libraries(pinyon_shift_thread_sampler PRIVATE dbghelp)
endif()

if(NOT PINYON_SHIFT_HOST_TESTS_ONLY)
pinyon_shift_attach_rexglue(pinyon_shift)
add_dependencies(pinyon_shift pinyon_shift_fh1_archive_extract)

# ReXGlue's SDL backend loads project overrides from the executable directory.
# Keep this as an always-built staging target so mapping-only updates do not
# require relinking the game host.
add_custom_target(pinyon_shift_stage_controller_mappings ALL
    COMMAND ${CMAKE_COMMAND}
        "-DSOURCE=${CMAKE_CURRENT_SOURCE_DIR}/config/gamecontrollerdb.txt"
        "-DDESTINATION=$<TARGET_FILE_DIR:pinyon_shift>/gamecontrollerdb.txt"
        -P "${PINYON_SHIFT_STAGE_FILE_SCRIPT}"
    DEPENDS pinyon_shift "${CMAKE_CURRENT_SOURCE_DIR}/config/gamecontrollerdb.txt"
    COMMENT "Staging project gamepad mappings beside pinyon_shift"
    VERBATIM)

if(WIN32)
    target_link_libraries(pinyon_shift PRIVATE bcrypt d3d12 dbghelp dxgi rex::gpu-fh1)
else()
    find_package(Threads REQUIRED)
    target_link_libraries(pinyon_shift PRIVATE Threads::Threads ${CMAKE_DL_LIBS} rex::gpu-fh1)
endif()

# The mod ABI header (NP-7) and the TOML parser mod.toml is read with.
target_include_directories(pinyon_shift PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${REXSDK_DIR}/thirdparty/tomlplusplus/include
    ${REXSDK_DIR}/thirdparty/renderdoc
    ${REXSDK_DIR})
endif()  # NOT PINYON_SHIFT_HOST_TESTS_ONLY

# Sample mods (NP-7.6): plain C libraries against include/pinyon_mod.h. Not
# part of the default build; tools/install-sample-mod.py copies one into a
# state directory's mods/.
add_library(pinyon_shift_mod_hello_telemetry MODULE EXCLUDE_FROM_ALL
    mods_src/samples/hello_telemetry/hello_telemetry.c)
target_include_directories(pinyon_shift_mod_hello_telemetry PRIVATE include)
set_target_properties(pinyon_shift_mod_hello_telemetry PROPERTIES
    OUTPUT_NAME hello_telemetry
    PREFIX ""
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/mods/hello_telemetry/code")
