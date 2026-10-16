using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using Microsoft.Win32;

namespace PinyonWheelSetup.Theming;

public enum ThemeChoice { Dark, Light, System }

/// <summary>Swaps the colour palette dictionary and keeps the window title bar in sync.</summary>
public static class ThemeManager
{
    private static bool hooked;

    public static ThemeChoice Choice { get; private set; } = ThemeChoice.Dark;
    public static bool IsDark { get; private set; } = true;

    public static void Apply(ThemeChoice choice)
    {
        Choice = choice;
        if (!hooked)
        {
            SystemEvents.UserPreferenceChanged += OnUserPreferenceChanged;
            hooked = true;
        }

        IsDark = choice switch
        {
            ThemeChoice.Light => false,
            ThemeChoice.System => SystemPrefersDark(),
            _ => true,
        };

        var app = Application.Current;
        var palette = new ResourceDictionary
        {
            // Entry-assembly pack URI; no assembly name needed.
            Source = new Uri($"pack://application:,,,/Themes/{(IsDark ? "Dark" : "Light")}.xaml", UriKind.Absolute),
        };
        app.Resources.MergedDictionaries[0] = palette; // index 0 is always the palette (see App.xaml)

        foreach (Window w in app.Windows) ApplyTitleBar(w);
    }

    public static bool SystemPrefersDark()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        return key?.GetValue("AppsUseLightTheme") is int v && v == 0;
    }

    private static void OnUserPreferenceChanged(object? sender, UserPreferenceChangedEventArgs e)
    {
        if (Choice == ThemeChoice.System && e.Category is UserPreferenceCategory.General or UserPreferenceCategory.Color)
            Application.Current?.Dispatcher.BeginInvoke(() => Apply(ThemeChoice.System));
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    public static void ApplyTitleBar(Window window)
    {
        IntPtr hwnd = new WindowInteropHelper(window).Handle;
        if (hwnd == IntPtr.Zero) return;
        int dark = IsDark ? 1 : 0;
        // DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win10 20H1+), 19 on older Win10 builds
        if (DwmSetWindowAttribute(hwnd, 20, ref dark, sizeof(int)) != 0)
            DwmSetWindowAttribute(hwnd, 19, ref dark, sizeof(int));
    }
}
