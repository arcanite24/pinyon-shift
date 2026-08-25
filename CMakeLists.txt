# Pinyon Shift - native ReXGlue host

cmake_minimum_required(VERSION 3.25)
project(pinyon_shift LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

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

if(WIN32)
    target_link_libraries(pinyon_shift PRIVATE dbghelp)
endif()
