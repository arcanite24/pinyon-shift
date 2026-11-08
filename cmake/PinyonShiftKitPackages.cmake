# Points every CMake package the ShiftGlue kit ships at the kit's copy.
#
# The kit's rexglue package finds its dependencies (SDL3, fmt, spdlog, the
# Vulkan headers) with find_dependency. Under a cross toolchain the search
# looks in the sysroot before the kit, and the sniper sysroot has its own
# SDL3 package whose libSDL3.a is not position-independent: the game's PIE
# executables and shared libraries then failed to link with "recompile with
# -fPIC" (#1001, #1005, #1009). <Package>_DIR is searched before any prefix,
# so setting it keeps the kit's packages, built with the runtime, in use.
# Normal variables also override a <Package>_DIR cached by an earlier
# configure that found the sysroot's copy.
function(pinyon_shift_use_kit_packages kit)
    file(GLOB _pinyon_kit_configs LIST_DIRECTORIES false
        "${kit}/lib/cmake/*/*Config.cmake" "${kit}/lib/cmake/*/*-config.cmake"
        "${kit}/share/cmake/*/*Config.cmake" "${kit}/share/cmake/*/*-config.cmake")
    foreach(_pinyon_config IN LISTS _pinyon_kit_configs)
        get_filename_component(_pinyon_dir "${_pinyon_config}" DIRECTORY)
        get_filename_component(_pinyon_name "${_pinyon_config}" NAME)
        string(REGEX REPLACE "(Config|-config)\\.cmake$" "" _pinyon_name "${_pinyon_name}")
        set(${_pinyon_name}_DIR "${_pinyon_dir}" PARENT_SCOPE)
    endforeach()
endfunction()
