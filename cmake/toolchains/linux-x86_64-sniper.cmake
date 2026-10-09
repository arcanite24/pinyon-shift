# x86-64 Linux against the Steam Runtime 3 "sniper" SDK sysroot
# (docs/LINUX_PORT_BACKLOG.md, LX-1.2).
#
# The pinned LLVM targets x86_64-linux-gnu inside the sysroot, so the binary
# needs glibc 2.31 at most and runs on SteamOS and current distributions. GCC
# 14's libstdc++ (C++23) is linked statically; libgcc_s.so.1 is on every
# glibc system. Nothing from the build host's own libraries is used.
#
# PINYON_LINUX_TOOLCHAIN (cache or environment) holds:
#   llvm/          LLVM 20.1.8 for the build host
#   sniper-sdk/    the SDK sysroot, absolute symlinks made relative
#   sniper-libgcc/ libgcc_s.so (linker script) and libgcc_eh.a from GCC 10,
#                  which the sysroot ships only beside GCC 10, not GCC 14
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)

if(NOT PINYON_LINUX_TOOLCHAIN)
  if(DEFINED ENV{PINYON_LINUX_TOOLCHAIN})
    set(PINYON_LINUX_TOOLCHAIN "$ENV{PINYON_LINUX_TOOLCHAIN}")
  else()
    get_filename_component(_pinyon_root "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
    set(PINYON_LINUX_TOOLCHAIN "${_pinyon_root}/.local/toolchain/linux-x86_64")
  endif()
endif()
set(PINYON_LINUX_TOOLCHAIN "${PINYON_LINUX_TOOLCHAIN}" CACHE PATH
    "Pinned LLVM, sniper sysroot and libgcc overlay for Linux builds")
# try_compile projects reload this file without the cache.
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES PINYON_LINUX_TOOLCHAIN)

set(_pinyon_llvm "${PINYON_LINUX_TOOLCHAIN}/llvm")
set(CMAKE_SYSROOT "${PINYON_LINUX_TOOLCHAIN}/sniper-sdk")
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
  set(CMAKE_${_pinyon_lang}_COMPILER_TARGET x86_64-linux-gnu)
  # Passed as --gcc-toolchain: clang takes GCC 14's headers and libstdc++
  # from here instead of GCC 10's in the sysroot's /usr/lib/gcc.
  set(CMAKE_${_pinyon_lang}_COMPILER_EXTERNAL_TOOLCHAIN "${CMAKE_SYSROOT}/usr/lib/gcc-14")
endforeach()

set(_pinyon_link "-fuse-ld=lld -L${PINYON_LINUX_TOOLCHAIN}/sniper-libgcc -static-libstdc++")
set(CMAKE_EXE_LINKER_FLAGS_INIT "${_pinyon_link}")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "${_pinyon_link}")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "${_pinyon_link}")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# pkg-config reads only the sysroot's .pc files.
set(ENV{PKG_CONFIG_SYSROOT_DIR} "${CMAKE_SYSROOT}")
set(ENV{PKG_CONFIG_LIBDIR}
    "${CMAKE_SYSROOT}/usr/lib/x86_64-linux-gnu/pkgconfig:${CMAKE_SYSROOT}/usr/share/pkgconfig")
set(ENV{PKG_CONFIG_PATH} "")
# SteamOS has no pkg-config of its own; the sysroot's runs on any host with
# GLib, which every Linux desktop has.
if(NOT CMAKE_HOST_WIN32 AND NOT PKG_CONFIG_EXECUTABLE)
  find_program(_pinyon_host_pkg_config NAMES pkg-config pkgconf NO_CMAKE_FIND_ROOT_PATH)
  if(NOT _pinyon_host_pkg_config)
    set(PKG_CONFIG_EXECUTABLE "${CMAKE_SYSROOT}/usr/bin/pkg-config" CACHE FILEPATH "")
  endif()
endif()

# SDL3's Wayland backend generates its protocol code at build time. The
# sysroot's scanner runs on a Linux build host with libxml2 (LX-1.4 replaces
# it with pregenerated sources so Windows can cross-build).
if(NOT CMAKE_HOST_WIN32 AND NOT WAYLAND_SCANNER)
  set(WAYLAND_SCANNER "${CMAKE_SYSROOT}/usr/bin/wayland-scanner" CACHE FILEPATH "")
endif()
