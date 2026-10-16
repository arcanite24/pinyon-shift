using System.Diagnostics;
using System.IO;
using System.Text;

namespace PinyonShift.Launcher.Wheel.Diagnostics;

/// <summary>
/// wheel-setup.log in the launcher's logs folder (or %TEMP% if that is not writable), for
/// troubleshooting. Every line is flushed at once so a hang or crash still leaves the last step.
/// A watchdog thread records the step the UI thread was in if it stops responding.
/// </summary>
public static class Log
{
    private static readonly object Gate = new();
    private static StreamWriter? writer;
    private static readonly Stopwatch Clock = Stopwatch.StartNew();

    // Watchdog: the UI thread marks what it is doing and beats every tick.
    private static volatile string step = "starting";
    private static long lastBeat = Environment.TickCount64;
    private static Thread? watchdog;

    public static string? FilePath { get; private set; }

    public static void Start(string? directory)
    {
        if (writer != null) return;
        string[] args = [];
        foreach (string candidate in new[] { directory ?? "", Path.GetTempPath() })
        {
            if (candidate.Length == 0) continue;
            try
            {
                Directory.CreateDirectory(candidate);
                string path = Path.Combine(candidate, "wheel-setup.log");
                writer = new StreamWriter(new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite),
                                          new UTF8Encoding(false)) { AutoFlush = true };
                FilePath = path;
                break;
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
        var version = typeof(Log).Assembly.GetName().Version;
        Write($"Pinyon Shift wheel setup (launcher {version}) started");
        Write($"  exe: {Environment.ProcessPath}");
        Write($"  args: {string.Join(' ', args)}");
        Write($"  OS: {Environment.OSVersion}, 64-bit process: {Environment.Is64BitProcess}, .NET {Environment.Version}");
        Write($"  extracted to: {AppContext.BaseDirectory}");
        bool emuWheel = Process.GetProcesses().Any(p => p.ProcessName.Contains("EmuWheel", StringComparison.OrdinalIgnoreCase));
        Write($"  EmuWheel running: {emuWheel}");

        watchdog = new Thread(Watch) { IsBackground = true, Name = "watchdog" };
        watchdog.Start();
    }

    public static void Write(string message)
    {
        string line = $"{DateTime.Now:HH:mm:ss.fff} +{Clock.Elapsed.TotalSeconds,8:F3} [{Environment.CurrentManagedThreadId,2}] {message}";
        lock (Gate)
        {
            try { writer?.WriteLine(line); }
            catch (IOException) { }
        }
        Debug.WriteLine(line);
    }

    public static void Error(string context, Exception e) => Write($"ERROR {context}: {e}");

    /// <summary>Marks what the UI thread is about to do, for the watchdog.</summary>
    public static void Step(string what) => step = what;

    public static void Beat() => Interlocked.Exchange(ref lastBeat, Environment.TickCount64);

    // The watchdog only watches while the wheel screen is open and beating.
    private static volatile bool watching;
    public static void Watching(bool on)
    {
        Beat();
        watching = on;
    }

    private static void Watch()
    {
        bool reported = false;
        while (true)
        {
            Thread.Sleep(1000);
            if (!watching) { reported = false; continue; }
            long silent = Environment.TickCount64 - Interlocked.Read(ref lastBeat);
            if (silent > 3000 && !reported)
            {
                Write($"WATCHDOG: the UI thread has not responded for {silent / 1000.0:F1} s; it was in: {step}");
                reported = true;
            }
            else if (silent <= 3000 && reported)
            {
                Write($"WATCHDOG: the UI thread is responding again (was stuck in: {step})");
                reported = false;
            }
        }
    }
}
