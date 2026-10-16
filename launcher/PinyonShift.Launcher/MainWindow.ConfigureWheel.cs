using System.Diagnostics;
using System.IO;
using System.Windows;

namespace PinyonShift.Launcher;

// Settings > Configure Wheel opens Pinyon Shift Configure (tools/wheel-setup), the racing wheel
// binder, when its EXE sits beside the launcher. Without it the button stays hidden.
public partial class MainWindow
{
    private const string ConfigureWheelExe = "PinyonShiftConfigure.exe";

    private static string ConfigureWheelPath => Path.Combine(AppContext.BaseDirectory, ConfigureWheelExe);

    private void ShowConfigureWheelButton() =>
        ConfigureWheelButton.Visibility = File.Exists(ConfigureWheelPath) ? Visibility.Visible : Visibility.Collapsed;

    private void ConfigureWheelButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            Process.Start(new ProcessStartInfo(ConfigureWheelPath)
            {
                UseShellExecute = true,
                WorkingDirectory = AppContext.BaseDirectory,
            });
            GraphicsStatusText.Text = "Pinyon Shift Configure is open. Its settings apply from the next game start.";
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or IOException or InvalidOperationException)
        {
            GraphicsStatusText.Text = $"{ConfigureWheelExe} could not start: {ex.Message}";
        }
    }
}
