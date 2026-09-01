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
        src/pinyon_shift_app.cpp
        src/pinyon_shift_diagnostics.cpp
        src/pinyon_shift_runtime_hooks.cpp
        src/native_renderer/graphics_hooks.cpp
        src/native_renderer/buffer_cache.cpp
        src/native_renderer/guest_output_renderer.cpp
        src/native_renderer/render_target_bridge.cpp
        src/native_renderer/resolve_assembly_tracker.cpp
        src/native_renderer/resource_worker.cpp
        src/native_renderer/resource_identity.cpp
        src/native_renderer/shader_capture.cpp
        src/native_renderer/shader_pack.cpp
        src/native_renderer/texture_cache.cpp
        src/native_renderer/texture_resource_bridge.cpp
    )
else()
    add_executable(pinyon_shift
        src/main.cpp
        src/pinyon_shift_app.cpp
        src/pinyon_shift_diagnostics.cpp
        src/pinyon_shift_runtime_hooks.cpp
        src/native_renderer/graphics_hooks.cpp
        src/native_renderer/buffer_cache.cpp
        src/native_renderer/guest_output_renderer.cpp
        src/native_renderer/render_target_bridge.cpp
        src/native_renderer/resolve_assembly_tracker.cpp
        src/native_renderer/resource_worker.cpp
        src/native_renderer/resource_identity.cpp
        src/native_renderer/shader_capture.cpp
        src/native_renderer/shader_pack.cpp
        src/native_renderer/texture_cache.cpp
        src/native_renderer/texture_resource_bridge.cpp
    )
endif()

add_executable(pinyon_shift_resource_identity_tests EXCLUDE_FROM_ALL
    tests/native_renderer/resource_identity_test.cpp
    src/native_renderer/resource_identity.cpp
)
target_include_directories(pinyon_shift_resource_identity_tests PRIVATE src)

add_executable(pinyon_shift_buffer_cache_tests EXCLUDE_FROM_ALL
    tests/native_renderer/buffer_cache_test.cpp
    src/native_renderer/buffer_cache.cpp
    src/native_renderer/resource_identity.cpp
)
target_include_directories(pinyon_shift_buffer_cache_tests PRIVATE src)

add_executable(pinyon_shift_texture_cache_tests EXCLUDE_FROM_ALL
    tests/native_renderer/texture_cache_test.cpp
    src/native_renderer/resource_identity.cpp
    src/native_renderer/texture_cache.cpp
)
target_include_directories(pinyon_shift_texture_cache_tests PRIVATE src)

add_executable(pinyon_shift_render_target_bridge_tests EXCLUDE_FROM_ALL
    tests/native_renderer/render_target_bridge_test.cpp
    src/native_renderer/render_target_bridge.cpp
    src/native_renderer/resource_identity.cpp
)
target_include_directories(pinyon_shift_render_target_bridge_tests PRIVATE src)

add_executable(pinyon_shift_resource_worker_tests EXCLUDE_FROM_ALL
    tests/native_renderer/resource_worker_test.cpp
    src/native_renderer/resource_worker.cpp
)
target_include_directories(pinyon_shift_resource_worker_tests PRIVATE src)

add_executable(pinyon_shift_resolve_assembly_tracker_tests EXCLUDE_FROM_ALL
    tests/native_renderer/resolve_assembly_tracker_test.cpp
    src/native_renderer/resolve_assembly_tracker.cpp
)
target_include_directories(pinyon_shift_resolve_assembly_tracker_tests PRIVATE src)

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
    target_link_libraries(pinyon_shift PRIVATE bcrypt dbghelp)
endif()
