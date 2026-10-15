using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;

namespace PinyonShift.Launcher.Desktop;

// One panel at a time under Play, as the Windows launcher's Settings, DLC,
// Radio and Android views (ShowPanel there); the open panel's button is
// outlined and a second click closes it.
public partial class MainWindow
{
    private enum Panel { None, Settings, Dlc, Radio, Android, Saves }

    private Panel _panel = Panel.None;

    private void ShowPanel(Panel panel)
    {
        // The local network share serves only while its panel is open.
        if (_panel == Panel.Android && panel != Panel.Android) StopAndroidShare();
        _panel = panel;
        SettingsPanel.IsVisible = panel == Panel.Settings;
        DlcPanel.IsVisible = panel == Panel.Dlc;
        RadioPanel.IsVisible = panel == Panel.Radio;
        AndroidPanel.IsVisible = panel == Panel.Android;
        SavesPanel.IsVisible = panel == Panel.Saves;
        foreach (var (button, owner) in new (Button, Panel)[]
                 {
                     (SettingsButton, Panel.Settings), (DlcButton, Panel.Dlc), (RadioButton, Panel.Radio),
                     (AndroidButton, Panel.Android), (SavesButton, Panel.Saves),
                 })
            button.Classes.Set("selected", owner == panel);
    }

    private async Task OpenPanelAsync(Panel panel)
    {
        if (_mode != Mode.Ready) return;
        if (_panel == panel)
        {
            ShowPanel(Panel.None);
            return;
        }
        ShowPanel(panel);
        StatusText.Text = "";
        // At 1280 x 800 (a Steam Deck) the panel starts below the fold.
        Avalonia.Threading.Dispatcher.UIThread.Post(() => PanelControl(panel)?.BringIntoView(),
            Avalonia.Threading.DispatcherPriority.Background);
        switch (panel)
        {
            case Panel.Settings: await LoadSettingsAsync(); break;
            case Panel.Dlc: await LoadDlcPanelAsync(); break;
            case Panel.Radio: await ChangeRadioAsync(Array.Empty<string>(), "Reading stations…", null); break;
            case Panel.Android: await LoadAndroidPanelAsync(); break;
            case Panel.Saves: SavesStatusText.Text = ""; break;
        }
    }

    private Control? PanelControl(Panel panel) => panel switch
    {
        Panel.Settings => SettingsPanel,
        Panel.Dlc => DlcPanel,
        Panel.Radio => RadioPanel,
        Panel.Android => AndroidPanel,
        Panel.Saves => SavesPanel,
        _ => null,
    };

    private async void SettingsButton_Click(object? sender, RoutedEventArgs e) => await OpenPanelAsync(Panel.Settings);
    private async void DlcButton_Click(object? sender, RoutedEventArgs e) => await OpenPanelAsync(Panel.Dlc);
    private async void RadioButton_Click(object? sender, RoutedEventArgs e) => await OpenPanelAsync(Panel.Radio);
    private async void AndroidButton_Click(object? sender, RoutedEventArgs e) => await OpenPanelAsync(Panel.Android);
    private async void SavesButton_Click(object? sender, RoutedEventArgs e) => await OpenPanelAsync(Panel.Saves);

    /// <summary>--snapshot FILE [STATE] [WIDTHxHEIGHT]: render the window to a
    /// PNG and exit, to check a layout without clicking. STATE is setup,
    /// building, ready, a panel (settings, dlc, radio, android, saves; loaded
    /// from the real backends), crash, or failure-graphics.</summary>
    public void Snapshot(string path, string? state, string? size)
    {
        if (size?.Split('x') is [var width, var height] && int.TryParse(width, out var w) && int.TryParse(height, out var h))
        {
            Width = w;
            Height = h;
        }
        Opened += async (_, _) =>
        {
            for (var i = 0; i < 600 && _mode == Mode.Loading; i++) await Task.Delay(100);
            await Task.Delay(500);
            switch (state)
            {
                case "ready":
                    ShowMode(Mode.Ready);
                    break;
                case "building":
                    ShowMode(Mode.Building);
                    Progress.Value = 47;
                    PercentText.Text = "47%";
                    ProgressMessage.Text = "Building the game (812/2140)";
                    break;
                case "settings" or "dlc" or "radio" or "android" or "saves":
                    ShowMode(Mode.Ready);
                    var panel = Enum.Parse<Panel>(state, ignoreCase: true);
                    await OpenPanelAsync(panel);
                    await Task.Delay(300);
                    PanelControl(panel)?.BringIntoView();
                    break;
                case "crash":
                    ShowMode(Mode.Ready);
                    ShowCrash(new CrashReport("pscrash-v1-0123456789abcdef0123", "pinyon-crash.zip",
                        $"{Repository}/issues/new", 1309));
                    break;
                case "failure-graphics":
                    ShowMode(Mode.Ready);
                    ShowLaunchResult(new CommandResult(1,
                        JsonDocument.Parse("""{"result":"graphics-unavailable","exit_code":28}""").RootElement, null));
                    break;
            }
            await Task.Delay(400);
            var pixels = new Avalonia.PixelSize((int)Bounds.Width, (int)Bounds.Height);
            using var bitmap = new Avalonia.Media.Imaging.RenderTargetBitmap(pixels);
            bitmap.Render(this);
            bitmap.Save(path);
            Close();
        };
    }
}
