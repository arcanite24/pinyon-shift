using System.Windows;
using PinyonWheelSetup.Diagnostics;
using PinyonWheelSetup.Theming;

namespace PinyonWheelSetup;

public partial class App : Application
{
    private readonly HashSet<string> shownErrors = [];

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        Log.Start(e.Args);
        AppDomain.CurrentDomain.UnhandledException += (_, a) =>
            Log.Write($"FATAL unhandled exception: {a.ExceptionObject}");
        TaskScheduler.UnobservedTaskException += (_, a) =>
        {
            Log.Error("unobserved task", a.Exception);
            a.SetObserved();
        };
        DispatcherUnhandledException += (_, a) =>
        {
            Log.Error("UI thread", a.Exception);
            a.Handled = true;
            // Show each distinct error once; a repeating one would stack dialogs every frame.
            if (shownErrors.Add(a.Exception.GetType().FullName + a.Exception.Message))
            {
                MessageBox.Show($"{a.Exception.Message}\n\nDetails are in {Log.FilePath}.",
                                "Pinyon Shift Configure", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        };
        var settings = AppSettings.Load();
        ThemeManager.Apply(settings.Theme);
        var window = new MainWindow(settings, e.Args);
        MainWindow = window;
        window.Show();
    }
}
