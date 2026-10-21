# NT and Unix clock conversions

NT file times count 100 ns intervals from 1601-01-01. Unix calendar time
uses 1970-01-01. A signed 64-bit nanosecond duration cannot represent 1601,
although a signed 64-bit 100 ns duration can represent it and year 9999.
Windows' standard library uses 100 ns system-clock ticks; the Linux
libstdc++ toolchain uses nanoseconds.

`WinSystemClock::to_sys` returns `std::chrono::sys_time<hundrednanoseconds>`.
It changes the epoch without narrowing to the host clock's native duration.
`from_sys` accepts a system time point with any duration, converts to NT
precision, then adjusts the epoch. Calendar recomposition in
`RtlTimeFieldsToTime` also uses a 100 ns system time point, so it does not
overflow before reaching the converter. Consumers must retain that duration
when working with dates outside their native `system_clock` range.

The caller audit covered these SDK paths:

| Path | Representation and result |
| --- | --- |
| `RtlTimeToTimeFields` / `RtlTimeFieldsToTime` | Both directions now retain 100 ns precision, including 1601 and 9999. |
| POSIX file metadata (`convertUnixtimeToWinFiletime`) | Multiplies Unix seconds by 10,000,000 and adds 116,444,736,000,000,000 NT ticks; no nanosecond clock intermediate. |
| Windows file metadata / host clock | Copies native FILETIME ticks directly. |
| POSIX `QueryHostSystemTime` | Adds the epoch offset to seconds, then converts seconds and microseconds to NT ticks. |
| `QueryGuestSystemTime` / `KeQuerySystemTime` | Operate on and return NT ticks directly. |
| STFS FAT and disc timestamps | Integer seconds-to-NT conversion or constant NT ticks. |
| Timers | Retain NT time points and use a separate relative-duration conversion to the steady clock; do not call `to_sys` or `from_sys`. |

The chrono regression tests retain the original NT-epoch assertions and add
year-9999 calendar round trips, 100 ns fractional values, Unix epoch boundary
ticks, and both 100 ns and nanosecond input durations, including nanosecond
minimum and maximum values. These are source-only tests without game data.

Validation on Multivac (Ryzen 7 5800X): LLVM 20.1.8 with the sniper
sysroot/libstdc++ in Ubuntu WSL and LLVM 20.1.8 with the MSVC standard
library on Windows each passed 299 SDK cases and 2,484 assertions. Both
runs retained the four existing BitStream skips. Builds used at most eight
parallel jobs. The Windows Release game build also passed with frozen
generated sources.
