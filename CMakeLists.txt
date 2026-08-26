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
    )
else()
    add_executable(pinyon_shift
        src/main.cpp
        src/pinyon_shift_app.cpp
        src/pinyon_shift_diagnostics.cpp
        src/pinyon_shift_runtime_hooks.cpp
    )
endif()

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
    target_link_libraries(pinyon_shift PRIVATE dbghelp)
endif()
