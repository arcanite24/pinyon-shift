using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;

namespace PinyonShift.Launcher.Desktop;

public partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var window = new MainWindow();
            desktop.MainWindow = window;
            // --snapshot FILE [setup|building|ready]: render the window to a
            // PNG and exit, to check the layout without a desktop.
            var args = desktop.Args ?? Array.Empty<string>();
            var index = Array.IndexOf(args, "--snapshot");
            if (index >= 0 && index + 1 < args.Length)
                window.Snapshot(args[index + 1], index + 2 < args.Length ? args[index + 2] : null);
        }
        base.OnFrameworkInitializationCompleted();
    }
}
