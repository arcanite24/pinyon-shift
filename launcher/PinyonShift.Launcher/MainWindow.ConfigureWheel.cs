using System.IO;
using System.Windows;

namespace PinyonShift.Launcher;

// The wheel screen (Wheel/WheelSetupView, what was Pinyon Shift Configure): Wheel on the main
// screen and Settings > Configure Wheel open it over the body; Done closes it. It reads and writes
// the game's pinyon_shift.toml, and reads devices through SDL only while it is open.
//
// --wheel-selftest <pinyon_shift.toml> <folder> opens it on that config, drives every binding step
// with SDL virtual devices, saves screenshots and selftest.log to the folder and quits.
public partial class MainWindow
{
    private const string WheelSelfTestArgument = "--wheel-selftest";
    private bool _wheelOpen;

    private string? WheelConfigPath =>
        _stateRoot is null ? null : Path.Combine(_stateRoot, "config", "pinyon_shift.toml");

    private string? WheelLogDirectory =>
        _repositoryRoot is null ? null : Path.Combine(_repositoryRoot, ".local", "logs");

    private async void WheelButton_Click(object sender, RoutedEventArgs e) => await OpenWheelAsync(null, null);

    private async Task OpenWheelAsync(string? config, string? selfTest)
    {
        if (_wheelOpen) return;
        _wheelOpen = true;
        WheelView.DoneRequested -= WheelView_DoneRequested;
        WheelView.DoneRequested += WheelView_DoneRequested;
        BodyScroll.Visibility = Visibility.Collapsed;
        WheelView.Visibility = Visibility.Visible;
        await WheelView.OpenAsync(config ?? WheelConfigPath, WheelLogDirectory ?? Path.GetTempPath(), selfTest);
    }

    private void CloseWheel()
    {
        if (!_wheelOpen) return;
        _wheelOpen = false;
        WheelView.Shutdown();
        WheelView.Visibility = Visibility.Collapsed;
        BodyScroll.Visibility = Visibility.Visible;
    }

    private void WheelView_DoneRequested(object? sender, EventArgs e)
    {
        CloseWheel();
        if (_wheelSelfTest) Application.Current.Shutdown();
    }

    private bool _wheelSelfTest;

    /// <summary>Runs the wheel screen's self-test when the launcher was started for it.</summary>
    private async Task<bool> RunWheelSelfTestIfAskedAsync()
    {
        var arguments = Environment.GetCommandLineArgs();
        int at = Array.IndexOf(arguments, WheelSelfTestArgument);
        if (at < 0 || at + 2 >= arguments.Length) return false;
        _wheelSelfTest = true;
        await OpenWheelAsync(arguments[at + 1], arguments[at + 2]);
        return true;
    }
}
