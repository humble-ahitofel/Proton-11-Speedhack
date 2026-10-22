/*
 * Proton SpeedHack runtime test.
 *
 * Build (any mingw-w64 toolchain):
 *   x86_64-w64-mingw32-gcc -O2 -o speedhack_test.exe speedhack_test.c -lwinmm
 *
 * Usage (inside the Proton SpeedHack prefix):
 *   speedhack_test.exe [auto]   drive the speed itself: 1x, 2x, 3x, toggling, back to 1x
 *   speedhack_test.exe watch    print the observed clock rate continuously, for manual
 *                               hotkey / Steam Input testing (Ctrl+C to quit)
 *
 * The reference clock is GetSystemTimePreciseAsFileTime(), which the SpeedHack
 * intentionally leaves unaccelerated.  Exit code: 0 = pass, 1 = failure,
 * 2 = speed control not available (only the 1x baseline was checked).
 */

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <mmsystem.h>

/* Wine-private NtSetSystemInformation class, see patches/wine and steam_helper/steam.c */
#define SystemWineSpeedhackInformation 0x5348
#define SPEEDHACK_MULTIPLIER_ONE 1000
#define SPEEDHACK_MULTIPLIER_MIN 10
#define SPEEDHACK_MULTIPLIER_MAX 100000

struct speedhack_info
{
    ULONG multiplier;
    ULONG prev_multiplier;
};

typedef LONG (WINAPI *NtSetSystemInformation_t)( int, void *, ULONG );
typedef void (WINAPI *QueryInterruptTime_t)( ULONGLONG * );

static NtSetSystemInformation_t pNtSetSystemInformation;
static QueryInterruptTime_t pQueryInterruptTime;
static LARGE_INTEGER qpc_freq;
static int failures;

static volatile LONG monotonic_stop;
static volatile LONG monotonic_errors;

static double real_seconds(void)
{
    FILETIME ft;
    ULARGE_INTEGER t;

    GetSystemTimePreciseAsFileTime( &ft );
    t.LowPart = ft.dwLowDateTime;
    t.HighPart = ft.dwHighDateTime;
    return t.QuadPart / 1e7;
}

static double qpc_seconds(void)
{
    LARGE_INTEGER c;
    QueryPerformanceCounter( &c );
    return (double)c.QuadPart / qpc_freq.QuadPart;
}

static double interrupt_seconds(void)
{
    ULONGLONG t = 0;
    if (pQueryInterruptTime) pQueryInterruptTime( &t );
    return t / 1e7;
}

static double unbiased_seconds(void)
{
    ULONGLONG t = 0;
    QueryUnbiasedInterruptTime( &t );
    return t / 1e7;
}

static double tick_seconds(void) { return GetTickCount64() / 1e3; }
static double timegettime_seconds(void) { return timeGetTime() / 1e3; }

/* returns 0 on success; multiplier 0 only queries the current speed */
static LONG set_speed( ULONG multiplier, ULONG *prev )
{
    struct speedhack_info info = { multiplier, ~0u };
    LONG status;

    if (!pNtSetSystemInformation) return -1;
    status = pNtSetSystemInformation( SystemWineSpeedhackInformation, &info, sizeof(info) );
    if (status) return status;
    /* an unpatched Wine stubs NtSetSystemInformation and returns success */
    if (info.prev_multiplier < SPEEDHACK_MULTIPLIER_MIN || info.prev_multiplier > SPEEDHACK_MULTIPLIER_MAX)
        return -2;
    if (prev) *prev = info.prev_multiplier;
    return 0;
}

/* hammer QueryPerformanceCounter and GetTickCount64 to catch any backwards step */
static DWORD WINAPI monotonic_thread( void *arg )
{
    LARGE_INTEGER last, now;
    ULONGLONG last_tick = GetTickCount64(), tick;

    QueryPerformanceCounter( &last );
    while (!monotonic_stop)
    {
        QueryPerformanceCounter( &now );
        if (now.QuadPart < last.QuadPart)
        {
            InterlockedIncrement( &monotonic_errors );
            printf( "  FAIL: QueryPerformanceCounter went backwards: %lld -> %lld\n",
                    (long long)last.QuadPart, (long long)now.QuadPart );
        }
        last = now;
        tick = GetTickCount64();
        if (tick < last_tick)
        {
            InterlockedIncrement( &monotonic_errors );
            printf( "  FAIL: GetTickCount64 went backwards: %llu -> %llu\n",
                    (unsigned long long)last_tick, (unsigned long long)tick );
        }
        last_tick = tick;
    }
    return 0;
}

struct clock_source
{
    const char *name;
    double (*get)(void);
    double granularity;  /* seconds */
};

static const struct clock_source clocks[] =
{
    { "QueryPerformanceCounter",    qpc_seconds,         0.0001 },
    { "timeGetTime",                timegettime_seconds, 0.002 },
    { "GetTickCount64",             tick_seconds,        0.040 },
    { "QueryInterruptTime",         interrupt_seconds,   0.040 },
    { "QueryUnbiasedInterruptTime", unbiased_seconds,    0.040 },
};
#define NB_CLOCKS (sizeof(clocks) / sizeof(clocks[0]))

static void check( BOOL ok, const char *fmt, ... )
{
    va_list args;

    printf( ok ? "  ok:   " : "  FAIL: " );
    va_start( args, fmt );
    vprintf( fmt, args );
    va_end( args );
    printf( "\n" );
    if (!ok) failures++;
}

/* measure all clocks against the real clock for the given duration */
static void measure_phase( const char *label, double expected, double duration )
{
    double start[NB_CLOCKS], end[NB_CLOCKS], real_start, real_end, real, sleep_start, slept;
    unsigned int i;

    printf( "%s (expected %.2fx):\n", label, expected );

    real_start = real_seconds();
    for (i = 0; i < NB_CLOCKS; i++) start[i] = clocks[i].get();
    Sleep( (DWORD)(duration * 1000) );
    real_end = real_seconds();
    for (i = 0; i < NB_CLOCKS; i++) end[i] = clocks[i].get();
    real = real_end - real_start;

    for (i = 0; i < NB_CLOCKS; i++)
    {
        double ratio = (end[i] - start[i]) / real;
        double tolerance = 0.03 + clocks[i].granularity * (expected + 1) / real;

        if (clocks[i].get == interrupt_seconds && !pQueryInterruptTime) continue;
        check( ratio > expected * (1 - tolerance) && ratio < expected * (1 + tolerance),
               "%-27s %.3fx", clocks[i].name, ratio );
    }

    /* waits are intentionally not accelerated (Cheat Engine semantics) */
    sleep_start = real_seconds();
    Sleep( 200 );
    slept = real_seconds() - sleep_start;
    printf( "  info: Sleep(200) took %.0f ms of real time\n", slept * 1000 );
}

/* switch speed and verify that QPC neither jumps nor goes backwards across the change */
static void switch_speed( ULONG multiplier, ULONG expected_prev, BOOL verbose )
{
    double q0, q1, r0, r1, max_speed;
    ULONG prev = 0;
    LONG status;

    q0 = qpc_seconds();
    r0 = real_seconds();
    status = set_speed( multiplier, &prev );
    q1 = qpc_seconds();
    r1 = real_seconds();

    max_speed = (multiplier > expected_prev ? multiplier : expected_prev) / 1000.0;
    if (!verbose && !status && prev == expected_prev &&
        q1 >= q0 && (q1 - q0) <= (r1 - r0) * max_speed + 0.005) return;

    check( !status, "set speed %.3fx (status %#lx)", multiplier / 1000.0, (unsigned long)status );
    check( prev == expected_prev, "previous speed reported as %.3fx", prev / 1000.0 );
    check( q1 >= q0 && (q1 - q0) <= (r1 - r0) * max_speed + 0.005,
           "QPC continuous across change (+%.3f ms QPC over %.3f ms real)",
           (q1 - q0) * 1000, (r1 - r0) * 1000 );
}

static int run_auto(void)
{
    ULONG initial = 0;
    HANDLE thread;
    LONG status;
    int i;

    status = set_speed( 0, &initial );
    if (status)
    {
        printf( "Speed control interface not available (status %#lx).\n", (unsigned long)status );
        printf( "Not running under Proton SpeedHack? Checking the 1x baseline only.\n\n" );
        measure_phase( "Baseline", 1.0, 1.5 );
        printf( "\n%s (speedhack not tested)\n", failures ? "FAILED" : "BASELINE PASSED" );
        return failures ? 1 : 2;
    }
    printf( "Initial speed %.3fx\n\n", initial / 1000.0 );
    if (initial != SPEEDHACK_MULTIPLIER_ONE) switch_speed( SPEEDHACK_MULTIPLIER_ONE, initial, TRUE );

    thread = CreateThread( NULL, 0, monotonic_thread, NULL, 0, NULL );

    measure_phase( "Normal speed", 1.0, 1.5 );

    switch_speed( 2000, 1000, TRUE );
    measure_phase( "Double speed", 2.0, 1.5 );

    switch_speed( 3000, 2000, TRUE );
    measure_phase( "Triple speed", 3.0, 1.5 );

    switch_speed( 1000, 3000, TRUE );
    measure_phase( "Back to normal speed", 1.0, 1.5 );

    printf( "Rapid toggling 1x <-> 2.5x (100 changes):\n" );
    for (i = 0; i < 50; i++)
    {
        switch_speed( 2500, 1000, FALSE );
        Sleep( 10 );
        switch_speed( 1000, 2500, FALSE );
        Sleep( 10 );
    }
    measure_phase( "Normal speed after toggling", 1.0, 1.5 );

    switch_speed( 500, 1000, TRUE );
    measure_phase( "Half speed", 0.5, 1.5 );
    switch_speed( 1000, 500, TRUE );

    printf( "Invalid multipliers:\n" );
    check( set_speed( 1, NULL ) != 0, "0.001x rejected" );
    check( set_speed( 1000000, NULL ) != 0, "1000x rejected" );

    monotonic_stop = 1;
    WaitForSingleObject( thread, INFINITE );
    CloseHandle( thread );
    check( !monotonic_errors, "QPC and GetTickCount64 monotonic during the whole run (%ld errors)",
           (long)monotonic_errors );

    printf( "\n%s (%d failure(s))\n", failures ? "FAILED" : "PASSED", failures );
    return failures ? 1 : 0;
}

static int run_watch(void)
{
    double q0 = qpc_seconds(), t0 = tick_seconds(), r0 = real_seconds();

    printf( "Press the SpeedHack hotkey to observe the clock rate (Ctrl+C to quit).\n" );
    for (;;)
    {
        double q1, t1, r1;
        ULONG speed = 0;

        Sleep( 500 );
        q1 = qpc_seconds();
        t1 = tick_seconds();
        r1 = real_seconds();
        if (set_speed( 0, &speed )) speed = 0;
        printf( "QPC rate %.2fx, GetTickCount64 rate %.2fx, configured %.3fx\n",
                (q1 - q0) / (r1 - r0), (t1 - t0) / (r1 - r0), speed / 1000.0 );
        q0 = q1; t0 = t1; r0 = r1;
    }
    return 0;
}

int main( int argc, char **argv )
{
    HMODULE ntdll = GetModuleHandleA( "ntdll.dll" );
    HMODULE kernelbase = GetModuleHandleA( "kernelbase.dll" );

    setvbuf( stdout, NULL, _IONBF, 0 );
    pNtSetSystemInformation = (NtSetSystemInformation_t)(void *)GetProcAddress( ntdll, "NtSetSystemInformation" );
    if (kernelbase)
        pQueryInterruptTime = (QueryInterruptTime_t)(void *)GetProcAddress( kernelbase, "QueryInterruptTime" );
    QueryPerformanceFrequency( &qpc_freq );
    timeBeginPeriod( 1 );

    if (argc > 1 && !strcmp( argv[1], "watch" )) return run_watch();
    if (argc > 1 && strcmp( argv[1], "auto" ))
    {
        printf( "usage: %s [auto|watch]\n", argv[0] );
        return 1;
    }
    return run_auto();
}
