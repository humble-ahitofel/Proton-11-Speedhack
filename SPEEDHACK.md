Proton SpeedHack 11
===================

A port of [LtSquigs' Proton SpeedHack](https://github.com/LtSquigs/Proton-SpeedHack)
(Proton 8.0) to Valve Proton **11.0-2e**.  While a hotkey is held (or after it
is toggled) the game's clocks run faster or slower, which speeds up or slows
down most games, similar to Cheat Engine's speedhack.

> **Status: implemented, not yet release-verified.**  The Wine patch, the
> `steam.exe` hotkey thread, the configuration and the build workflow are in
> place.  See [Verification status](#verification-status) for what has and has
> not been tested.  Do not treat a build as a working release until the
> runtime tests below have passed on the compiled distribution.

Installing
----------

1. Run the **Build Proton SpeedHack** workflow (Actions tab, see
   [Building](#building)) or build locally.
2. Download the `proton-11.0-2e-speedhack` artifact, unzip it, and extract the
   tarball into `~/.steam/root/compatibilitytools.d/`
   (Flatpak Steam: `~/.var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d/`):

   ```bash
   mkdir -p ~/.steam/root/compatibilitytools.d
   tar -xJf proton-11.0-2e-speedhack.tar.xz -C ~/.steam/root/compatibilitytools.d/
   ```
3. Restart Steam and select the tool under *Properties → Compatibility* of a game.

Usage and configuration
-----------------------

By default holding **Page Up** runs the game at **2.5×**.

Each setting is taken from the first source that provides a valid value:

1. Environment variables, e.g. in the Steam launch options:
   `SPEEDHACK_SPEED=3 SPEEDHACK_TOGGLE=1 SPEEDHACK_KEYS=ctrl,f12 %command%`
2. `~/.speedhack/<SteamGameId>.json` (per game, e.g. `~/.speedhack/570.json`)
3. `~/.speedhack/speedhack.json`
4. `speedhack.json` in the compatibility tool directory
5. Built-in defaults

```json
{
    "speed": 2.5,
    "toggle": 0,
    "keys": "page_up"
}
```

| Setting  | Values | Meaning |
|----------|--------|---------|
| `speed`  | 0.01 – 100 | Clock multiplier while active (values below 1 slow the game down). |
| `toggle` | `0`/`1`, `true`/`false` | `0`: active while the keys are held. `1`: each press toggles. |
| `keys`   | string (`"ctrl,f12"`) or list (`["ctrl","f12"]`), up to 4 keys; `""` disables | All listed keys must be pressed together. |

`"key"` is accepted as an alias of `"keys"` (the original documented `keys`
but read `key`).  Invalid values are ignored with a message in the Proton log
(`PROTON_LOG=1`) and the next source is used.

Key names: `a`–`z`, `0`–`9`, `f1`–`f24`, `num0`–`num9`, `page_up`,
`page_down`, `home`, `end`, `insert`, `delete`, `up`, `down`, `left`, `right`,
`space`, `enter`/`return`, `tab`, `back`/`backspace`, `esc`/`escape`, `pause`,
`caps_lock`, `numlock`, `scroll_lock`, `shift`, `control`/`ctrl`, `alt`,
`left_shift`, `right_shift`, `left_control`, `right_control`, `left_alt`,
`right_alt`, `left_win`, `right_win`, `multiply`, `add`, `separator`,
`subtract`, `decimal`, `divide`, `semicolon`, `plus`, `comma`, `minus`,
`period`, `forward_slash`, `tilde`, `left_bracket`, `back_slash`,
`right_bracket`, `quote`.  Any Windows virtual-key code can also be given as a
number (`"0x7b"` or `"123"`).  See `proton_speedhack.py`.

### Steam Input / controllers

The hotkey is read with `GetAsyncKeyState`, so anything that produces the
configured keyboard key works, including Steam Input: bind a controller button
(or a Steam Deck back grip) to the configured key, e.g. *Page Up*, in the
game's controller layout.

### Changes compared to the Proton 8.0 SpeedHack

* `QueryPerformanceCounter` is now accelerated at full resolution; the
  original derived it from the 16 ms `InterruptTime`.
* The speed is re-anchored on every change, so clocks never jump when toggling.
* Wait timeouts are no longer mixed up between real and accelerated time.
* The `SIGUSR1`/`SIGUSR2` remote control was dropped: Proton 11's `steam.exe`
  is a Windows (PE) program and cannot install Unix signal handlers.
* Fixed the `k`–`n` key codes and the `key`/`keys` JSON mismatch.

How it works
------------

| Component | File |
|-----------|------|
| Wine patch (wineserver + ntdll) | `patches/wine/0001-ntdll-server-Add-Proton-SpeedHack-clock-scaling.patch` |
| Patch applier | `patches/apply-wine-patches.sh` |
| Hotkey thread | `steam_helper/steam.c` (`speedhack_thread`) |
| Configuration | `proton_speedhack.py`, `speedhack.json`, hook in `proton` |
| Runtime test | `speedhack_test/speedhack_test.c` |
| Config unit tests | `speedhack_test/test_proton_speedhack.py` |

**Wine.**  The wineserver owns a per-prefix multiplier (1/1000 units, 10 –
100000).  On every change it re-anchors (`fake = fake_anchor + (real -
real_anchor) × multiplier`) so accelerated time is continuous, and publishes
`{seq, multiplier, real_anchor, fake_anchor}` under a sequence lock at offset
`0xf00` of the `KUSER_SHARED_DATA` page (the structure itself ends at
`0x738`).  ntdll's `NtQueryPerformanceCounter` scales its own
`CLOCK_MONOTONIC_RAW` reading with these anchors, so QPC keeps its full
resolution and needs no server round trip.  The wineserver writes scaled
`InterruptTime`/`TickCount` into `KUSER_SHARED_DATA` and uses scaled time for
message timestamps.  The speed is set through the Wine-private
`NtSetSystemInformation( SystemWineSpeedhackInformation = 0x5348, { multiplier,
prev_multiplier }, 8 )` class, implemented by a new `set_speedhack_multiplier`
server request.  Until the speed is first changed every clock is bit-for-bit
identical to upstream Proton, and at 1× the accelerated clock equals the real
one plus a constant offset accumulated by earlier acceleration.

| Accelerated | Not accelerated (by design) |
|-------------|-----------------------------|
| `QueryPerformanceCounter` / `NtQueryPerformanceCounter` | `GetSystemTime*`, `NtQuerySystemTime` (wall clock) |
| `timeGetTime` (QPC based in Wine 11) | `Sleep`, `NtDelayExecution`, wait timeouts |
| `GetTickCount`, `GetTickCount64` | Waitable timers, `SetTimer`/`WM_TIMER`, server timers |
| `QueryInterruptTime`, `QueryUnbiasedInterruptTime` | fsync/esync/ntsync timeouts |
| Window message times (`GetMessageTime`) | `RDTSC` executed directly by the game |

Waits stay real so that frame limiters and audio keep working; games that only
time themselves with sleeps are not sped up, exactly like with the original.
ntdll converts relative timeouts with the *real* monotonic clock
(`server_wait`, `NtDelayExecution`, `NtQueryTimer`) because the wineserver
schedules them on real time.

**steam.exe.**  When `PROTON_SPEEDHACK_KEYS` is set, the game's `steam.exe`
wrapper resets the speed to 1× before launching the game (the wineserver may
be reused), then starts a thread that polls the configured keys every 20 ms and
switches between 1× and the configured multiplier.  When the game exits the
thread is stopped and the speed is reset to 1×.

**proton.**  `proton_speedhack.py` resolves the configuration and passes
`PROTON_SPEEDHACK_MULTIPLIER`, `PROTON_SPEEDHACK_TOGGLE` and
`PROTON_SPEEDHACK_KEYS` to `steam.exe`.

### Known limitations

* The speed is global for a wineserver, i.e. for every process in the prefix.
* `timeSetEvent` multimedia timers, which re-arm using `timeGetTime`, fire in
  bursts while accelerated.
* X11 event timestamps are converted with the real rate; Vulkan/DXVK
  calibrated timestamps are not scaled.  Games using either for timing may
  behave oddly while accelerated.
* Audio: winepulse (Proton's default) only uses QPC for timestamps reported to
  the game.  The ALSA/OSS drivers schedule their period loop with QPC but sleep
  in real time, so with the ALSA fallback they wake up more often while
  accelerated.
* Games reading the TSC directly (`RDTSC`) are not affected.
* The `KUSER_SHARED_DATA` tail offset and info class `0x5348` are a private
  convention between this patch, `steam.exe` and the test program.
* Only x86_64 builds have been considered; ARM64 is untested.

Building
--------

### GitHub Actions (recommended)

`.github/workflows/build-speedhack.yml` is a manually triggered
(`workflow_dispatch`) workflow:

1. Frees disk space on GitHub-hosted runners (optional) and checks CPU, RAM
   and disk against configurable minimums (defaults 4 CPUs, 15 GiB RAM, 55 GiB
   disk) before doing anything expensive.
2. Checks out all submodules, applies `patches/wine/*.patch` to Valve's pinned
   `wine` submodule, and builds `make redist` in Valve's Proton SDK container
   (`configure.sh --container-engine=docker`).
3. Caches ccache and the cargo registry with `actions/cache` (saved even if the
   build fails, so a retry continues where it stopped).
4. Verifies the distribution, packages it as `<build_name>.tar.xz` (top-level
   directory `<build_name>/`, ready for `compatibilitytools.d`) plus a
   `.sha256`, and uploads it.  Build, configure and resource logs are uploaded
   as `<build_name>-logs` even on failure.

Runner choice: a full build takes several hours with 4 cores.  The standard
`ubuntu-latest` runner (4 CPUs, 16 GB RAM, 6 h job limit) is borderline in
time and needs the disk clean-up; a larger GitHub-hosted runner (e.g. a
16-core label configured for the repository, billed per minute) or a
self-hosted runner with Docker is recommended.  Pass the label as `runner`,
or a JSON array such as `["self-hosted","linux","x64"]`.  Nothing is built
automatically.

`.github/workflows/speedhack-checks.yml` runs the cheap source-level checks
(patch applies to the pinned wine, `make_requests` regenerates the protocol,
configuration unit tests, test program compiles) on pull requests.

### Locally

```bash
git submodule update --init --recursive
patches/apply-wine-patches.sh          # idempotent; --check to only verify
mkdir build && cd build
../configure.sh --enable-ccache --build-name=proton-11.0-2e-speedhack
make redist                            # or: make install
```

Generated Wine files (`include/wine/server_protocol.h`,
`server/request_handlers.h`, `server/request_trace.h`,
`dlls/ntdll/ntsyscalls.h`) are intentionally not in the patch; Proton's build
regenerates them.

### Updating to a new Proton release

1. Merge the new Valve Proton tag into this repository and keep
   `.gitmodules` pointing `wine` at `https://github.com/ValveSoftware/wine.git`.
2. Run `patches/apply-wine-patches.sh --check`.  If the patch no longer applies,
   apply it with `git -C wine am -3 ../patches/wine/*.patch`, resolve the
   conflicts, and regenerate it with
   `git -C wine format-patch -1 -o ../patches/wine/` (then reset the submodule).
3. Re-check that `NtQueryPerformanceCounter`, `server_wait`,
   `NtDelayExecution` and `NtQueryTimer` in `dlls/ntdll/unix/sync.c` /
   `server.c`, and `set_user_shared_data_time` in `server/fd.c`, still use the
   clocks as described above, and that `KUSER_SHARED_DATA` still ends before
   offset `0xf00`.
4. Re-run the runtime tests.

Testing
-------

### Source-level (no Proton build needed)

```bash
patches/apply-wine-patches.sh --check
python3 speedhack_test/test_proton_speedhack.py
make -C speedhack_test                 # needs mingw-w64
```

### Runtime

`speedhack_test.exe` (and `speedhack_test32.exe` for WoW64) measure the
accelerated clocks against the unaccelerated wall clock.  Copy them into the
game prefix or any directory and run them with the built Proton:

```bash
export STEAM_COMPAT_DATA_PATH=/tmp/speedhack-pfx STEAM_COMPAT_CLIENT_INSTALL_PATH=~/.steam/root
mkdir -p "$STEAM_COMPAT_DATA_PATH"
~/.steam/root/compatibilitytools.d/proton-11.0-2e-speedhack/proton run speedhack_test.exe
```

* `speedhack_test.exe` (`auto` mode) sets the speed itself and checks QPC,
  `GetTickCount64`, `timeGetTime` and `QueryInterruptTime` at 1×, 2×, 3×,
  rapid toggling (continuity and monotonicity), 0.5×, invalid values and the
  return to 1×.  Exit code 0 = passed, 1 = failed, 2 = speed control not
  available (unpatched Wine; only the 1× baseline was checked).
* `speedhack_test.exe watch` prints the observed rate twice a second; use it to
  test the hotkey (hold/toggle) and Steam Input bindings by hand.  When
  launched outside Steam, `steam.exe` is not involved, so set the speed with
  the `auto` mode or test the hotkeys from a Steam shortcut to the test
  program (add it as a non-Steam game with this compatibility tool).

Verification status
-------------------

| Item | Status |
|------|--------|
| Patch applies to Valve wine `e60892cc` (Proton 11.0-2e) | verified locally (also checked by `speedhack-checks.yml`) |
| `make_requests` regenerates the protocol with the new request | verified locally |
| Configuration resolution (`proton_speedhack.py`) | unit tested |
| Test program compiles (x86_64, i686) | verified with mingw-w64 |
| Patched Wine 11 (standalone headless build, not the Proton container) + `speedhack_test.exe` / `speedhack_test32.exe` | **passed** (1×, 2×, 3×, toggling, 0.5×, back to 1×, invalid values, monotonicity) |
| `steam.exe` hotkey thread at runtime, Steam Input | **not verified** |
| Full `make redist` build in the Proton SDK container | **not run yet** |
| Games under the compiled distribution | **not verified** |
