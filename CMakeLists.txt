# Pinyon Shift - native ReXGlue host

cmake_minimum_required(VERSION 3.25)
project(pinyon_shift LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# SDL uses native Windows HID and XInput backends here. Its optional libusb
# probe is for platforms/controllers that need direct USB access and should not
# make a normal Windows build look like it has a missing dependency.
if(WIN32)
    set(SDL_HIDAPI_LIBUSB OFF CACHE BOOL "Disable optional libusb HID backend on Windows" FORCE)
endif()

include(cmake/PinyonShiftRexGlue.cmake)

if(WIN32)
    add_executable(pinyon_shift WIN32
        src/main.cpp
        src/fh1_render_test.cpp
        src/pinyon_shift_app.cpp
        src/pinyon_shift_diagnostics.cpp
        src/pinyon_shift_runtime_hooks.cpp
        src/ui/fh1_ui_api.cpp
        src/native_renderer/graphics_hooks.cpp
        src/native_renderer/fh1_gpu_corpus.cpp
        src/native_renderer/fh1_pass_tracker.cpp
        src/native_renderer/guest_output_renderer.cpp
        src/native_renderer/native_output_track.cpp
        src/native_renderer/native_output_triangle.cpp
        src/native_renderer/snr04_owned_scene_diagnostic.cpp
        src/native_renderer/shader_capture.cpp
    )
else()
    add_executable(pinyon_shift
        src/main.cpp
        src/fh1_render_test.cpp
        src/pinyon_shift_app.cpp
        src/pinyon_shift_diagnostics.cpp
        src/pinyon_shift_runtime_hooks.cpp
        src/ui/fh1_ui_api.cpp
        src/native_renderer/graphics_hooks.cpp
        src/native_renderer/fh1_gpu_corpus.cpp
        src/native_renderer/fh1_pass_tracker.cpp
        src/native_renderer/guest_output_renderer.cpp
        src/native_renderer/shader_capture.cpp
    )
endif()

add_executable(pinyon_shift_fh1_execution_key_tests EXCLUDE_FROM_ALL
    tests/native_renderer/fh1_execution_key_test.cpp
)

add_executable(pinyon_shift_fh1_ui_api_tests EXCLUDE_FROM_ALL
    tests/ui/fh1_ui_api_test.cpp
    src/ui/fh1_ui_api.cpp
)
target_include_directories(pinyon_shift_fh1_ui_api_tests PRIVATE src)
target_include_directories(pinyon_shift_fh1_execution_key_tests PRIVATE
    ${REXSDK_DIR}/include)

add_executable(pinyon_shift_fh1_pass_tracker_tests EXCLUDE_FROM_ALL
    tests/native_renderer/fh1_pass_tracker_test.cpp
    src/native_renderer/fh1_pass_tracker.cpp
)
target_include_directories(pinyon_shift_fh1_pass_tracker_tests PRIVATE
    src ${REXSDK_DIR}/include)

add_executable(pinyon_shift_fh1_shader_pack_tests EXCLUDE_FROM_ALL
    tests/native_renderer/fh1_shader_pack_test.cpp
    ${REXSDK_DIR}/src/graphics/d3d12/fh1_shader_pack.cpp
)
target_include_directories(pinyon_shift_fh1_shader_pack_tests PRIVATE
    ${REXSDK_DIR}/include)
target_link_libraries(pinyon_shift_fh1_shader_pack_tests PRIVATE rex::runtime)
if(WIN32)
    target_link_libraries(pinyon_shift_fh1_shader_pack_tests PRIVATE bcrypt)
    # Standalone D3D12 conformance test: no renderer/runtime library dependency.
    add_executable(pinyon_shift_fh1_owned_geometry_tests EXCLUDE_FROM_ALL
        tests/native_renderer/fh1_owned_geometry_test.cpp)
    target_link_libraries(pinyon_shift_fh1_owned_geometry_tests PRIVATE d3d12 dxgi)
    add_executable(pinyon_shift_snr04_owned_scene_diagnostic EXCLUDE_FROM_ALL
        tests/native_renderer/snr04_owned_scene_diagnostic_main.cpp
        src/native_renderer/snr04_owned_scene_diagnostic.cpp)
    target_include_directories(pinyon_shift_snr04_owned_scene_diagnostic PRIVATE src)
    target_link_libraries(pinyon_shift_snr04_owned_scene_diagnostic PRIVATE
        bcrypt d3d12 d3dcompiler dxgi xxhash)
endif()

add_executable(pinyon_shift_fh1_archive_extract EXCLUDE_FROM_ALL
    tools/fh1_archive_extract.cpp
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
    ${REXSDK_DIR}/include)
target_link_libraries(pinyon_shift_fh1_archive_extract PRIVATE rex::runtime)

pinyon_shift_attach_rexglue(pinyon_shift)

# ReXGlue's SDL backend loads project overrides from the executable directory.
# Keep this as an always-built staging target so mapping-only updates do not
# require relinking the game host.
add_custom_target(pinyon_shift_stage_controller_mappings ALL
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/config/gamecontrollerdb.txt"
        "$<TARGET_FILE_DIR:pinyon_shift>/gamecontrollerdb.txt"
    DEPENDS pinyon_shift "${CMAKE_CURRENT_SOURCE_DIR}/config/gamecontrollerdb.txt"
    COMMENT "Staging project gamepad mappings beside pinyon_shift"
    VERBATIM)

if(WIN32)
    target_link_libraries(pinyon_shift PRIVATE bcrypt d3d12 d3dcompiler dbghelp dxgi rex::gpu-fh1)
endif()
