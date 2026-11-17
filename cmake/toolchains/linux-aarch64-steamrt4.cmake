# AArch64 Linux against the Steam Runtime 4 arm64 SDK sysroot
# (docs/LINUX_ARM64_RESEARCH.md, LA-1).
#
# Valve publishes no arm64 "sniper" SDK; steamrt4 (Debian 13) is the arm64
# runtime it does publish, so the binary needs glibc 2.41 at most. GCC 14 is
# the sysroot's own compiler, so clang finds its headers, libstdc++ and
# libgcc without an overlay. libstdc++ is linked statically as on x86-64.
#
# PINYON_LINUX_TOOLCHAIN (cache or environment) holds:
#   llvm/          LLVM 20.1.8 for the build host (any release build targets
#                  AArch64 as well)
#   steamrt4-sdk/  the SDK sysroot, absolute symlinks made relative
#   bin/           optional host wrappers (ld.lld, wayland-scanner) as in the
#                  x86-64 toolchain; the sysroot's own tools are AArch64
#                  binaries and cannot run on an x86-64 build host
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

if(NOT PINYON_LINUX_TOOLCHAIN)
  if(DEFINED ENV{PINYON_LINUX_TOOLCHAIN})
    set(PINYON_LINUX_TOOLCHAIN "$ENV{PINYON_LINUX_TOOLCHAIN}")
  else()
    get_filename_component(_pinyon_root "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
    set(PINYON_LINUX_TOOLCHAIN "${_pinyon_root}/.local/toolchain/linux-aarch64")
  endif()
endif()
set(PINYON_LINUX_TOOLCHAIN "${PINYON_LINUX_TOOLCHAIN}" CACHE PATH
    "Pinned LLVM and steamrt4 arm64 sysroot for Linux AArch64 builds")
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES PINYON_LINUX_TOOLCHAIN)

set(_pinyon_llvm "${PINYON_LINUX_TOOLCHAIN}/llvm")
set(CMAKE_SYSROOT "${PINYON_LINUX_TOOLCHAIN}/steamrt4-sdk")
if(CMAKE_HOST_WIN32)
  set(_pinyon_exe ".exe")
else()
  set(_pinyon_exe "")
endif()
set(CMAKE_C_COMPILER "${_pinyon_llvm}/bin/clang${_pinyon_exe}")
set(CMAKE_CXX_COMPILER "${_pinyon_llvm}/bin/clang++${_pinyon_exe}")
set(CMAKE_ASM_COMPILER "${CMAKE_C_COMPILER}")
set(CMAKE_AR "${_pinyon_llvm}/bin/llvm-ar${_pinyon_exe}" CACHE FILEPATH "")
set(CMAKE_RANLIB "${_pinyon_llvm}/bin/llvm-ranlib${_pinyon_exe}" CACHE FILEPATH "")
foreach(_pinyon_lang C CXX ASM)
  set(CMAKE_${_pinyon_lang}_COMPILER_TARGET aarch64-linux-gnu)
endforeach()

set(_pinyon_link "-fuse-ld=lld -static-libstdc++")
set(_pinyon_wrappers "${PINYON_LINUX_TOOLCHAIN}/bin")
if(NOT CMAKE_HOST_WIN32 AND EXISTS "${_pinyon_wrappers}/ld.lld")
  string(APPEND _pinyon_link " \"--ld-path=${_pinyon_wrappers}/ld.lld\"")
endif()
set(CMAKE_EXE_LINKER_FLAGS_INIT "${_pinyon_link}")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "${_pinyon_link}")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "${_pinyon_link}")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# pkg-config reads only the sysroot's .pc files. The host's pkg-config is
# used: the sysroot's is an AArch64 binary.
set(ENV{PKG_CONFIG_SYSROOT_DIR} "${CMAKE_SYSROOT}")
set(ENV{PKG_CONFIG_LIBDIR}
    "${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/pkgconfig:${CMAKE_SYSROOT}/usr/share/pkgconfig")
set(ENV{PKG_CONFIG_PATH} "")

# SDL3's Wayland backend generates its protocol code at build time, which
# needs a scanner that runs on the build host. Its output does not depend on
# the target, so the x86-64 toolchain's wrapper serves.
if(NOT CMAKE_HOST_WIN32 AND NOT WAYLAND_SCANNER)
  if(EXISTS "${_pinyon_wrappers}/wayland-scanner")
    set(WAYLAND_SCANNER "${_pinyon_wrappers}/wayland-scanner" CACHE FILEPATH "")
  else()
    find_program(WAYLAND_SCANNER wayland-scanner NO_CMAKE_FIND_ROOT_PATH)
  endif()
endif()
