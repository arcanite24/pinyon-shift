using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;

namespace PinyonShift.Launcher.Desktop;

// Settings read before the game starts (GraphicsPanel on Windows): the
// internal resolution, output scaling and Treasure Map through pinyon.py
// config, reset and restore of the settings file, and the hardware check
// with its recommended preset through pinyon.py hardware. The rest is in
// game (F6).
public partial class MainWindow
{
    private const string InGameHint = "Everything else is in the game: press F6 while playing.";
    private JsonElement? _graphicsSettings;
    private JsonElement? _hardware;

    private async Task<JsonElement?> HardwareAsync()
    {
        if (_hardware is not null || _installation is null) return _hardware;
        var result = await _installation.RunJsonAsync(["hardware"]);
        if (result.Succeeded) _hardware = result.Json;
        else AppendLog($"Hardware check: {result.Error("The hardware check")}");
        return _hardware;
    }

    private async Task LoadSettingsAsync()
    {
        GraphicsStatusText.Text = InGameHint;
        var result = await RunConfigAsync("get");
        if (result.Succeeded) ApplyGraphicsResult(result.Json!.Value);
        else GraphicsStatusText.Text = $"Settings could not be loaded: {result.Error("The settings tool")}";
        await ShowHardwareCheckAsync();
    }

    private Task<CommandResult> RunConfigAsync(string action, IEnumerable<string>? options = null) =>
        _installation!.RunJsonAsync(new[] { "config", action }.Concat(options ?? []).Concat(StateArguments()));

    // Only the choices in this panel: the rest is set in game and must not
    // be overwritten.
    private string[] PanelChoices() =>
    [
        "--resolution-scale", SelectedTag(ResolutionCombo, "1"), "--graphics-api", "vulkan",
        "--output-scaling", SelectedTag(OutputScalingCombo, "bilinear"),
        "--treasure-map", TreasureMapCheck.IsChecked == true ? "true" : "false",
    ];

    private static string SelectedTag(ComboBox box, string fallback) =>
        (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? fallback;

    private static void SelectTag(ComboBox box, string value) =>
        box.SelectedItem = box.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => string.Equals(item.Tag?.ToString(), value, StringComparison.OrdinalIgnoreCase))
            ?? box.SelectedItem;

    private void ApplyGraphicsResult(JsonElement result)
    {
        if (!result.TryGetProperty("settings", out var settings)) return;
        _graphicsSettings = settings.Clone();
        SelectTag(ResolutionCombo, settings.TryGetProperty("resolution_scale", out var scale) ? scale.ToString() : "1");
        SelectTag(OutputScalingCombo, settings.TryGetProperty("output_scaling", out var scaling) &&
            scaling.GetString() is { Length: > 0 } value ? value : "bilinear");
        TreasureMapCheck.IsChecked = !settings.TryGetProperty("treasure_map", out var map) || map.GetBoolean();
        UpdateResolutionLine();
        UpdateRecommendationText();
    }

    private string? Setting(string name) =>
        _graphicsSettings is { } settings && settings.TryGetProperty(name, out var value) ? value.ToString() : null;

    private int SettingInt(string name) => int.TryParse(Setting(name), out var value) ? value : 0;

    private bool SettingBool(string name, bool fallback) =>
        _graphicsSettings is { } settings && settings.TryGetProperty(name, out var value)
            && value.ValueKind is JsonValueKind.True or JsonValueKind.False ? value.GetBoolean() : fallback;

    private void GraphicsChoice_Changed(object? sender, SelectionChangedEventArgs e) => UpdateResolutionLine();

    // The resolution line's verb for an output scaling tag. Linux and macOS
    // builds compile AMD's FidelityFX library for FSR 2 and 3; DLSS is built
    // only on Windows, so here it runs as FSR 1, as the in-game line says.
    private static string UpscalerVerb(string? scaling) => scaling switch
    {
        "fsr" => "FSR 1 upscales",
        "fsr2" => "FSR 2 upscales",
        "fsr3" => "FSR 3 upscales",
        "dlss" => "FSR 1 (DLSS is Windows only) upscales",
        _ => "stretched",
    };

    // What the game renders and what reaches the screen, as the in-game
    // display settings say it: the scaled 1280 x 720 image, fitted to the
    // display (or the window) with the chosen output scaling.
    private void UpdateResolutionLine()
    {
        if (ResolutionLineText is null) return;
        var scale = int.TryParse(SelectedTag(ResolutionCombo, "1"), out var value) ? value : 1;
        var (renderWidth, renderHeight) = (1280 * scale, 720 * scale);
        var line = $"Renders {renderWidth} × {renderHeight}";
        if (OutputSize() is not var (outputWidth, outputHeight))
        {
            ResolutionLineText.Text = line + ".";
            return;
        }
        var scaling = SelectedTag(OutputScalingCombo, "bilinear");
        ResolutionLineText.Text = (long)outputWidth * outputHeight == (long)renderWidth * renderHeight
            ? $"{line}, the size of your screen."
            : (long)outputWidth * outputHeight > (long)renderWidth * renderHeight
                ? $"{line}, {UpscalerVerb(scaling)} to {outputWidth} × {outputHeight}."
                : $"{line}, downscaled to {outputWidth} × {outputHeight}.";
    }

    private (int Width, int Height)? OutputSize()
    {
        (int Width, int Height)? area = null;
        var scaling = Screens.ScreenFromWindow(this)?.Scaling ?? 1;
        if (_graphicsSettings is null || SettingBool("fullscreen", true))
        {
            // Monitor 0 and 1 are the primary display, 2 on the others.
            var monitor = SettingInt("monitor");
            var screen = monitor > 1
                ? Screens.All.Where(screen => !screen.IsPrimary).Skip(monitor - 2).FirstOrDefault()
                : Screens.Primary;
            screen ??= Screens.Primary;
            if (screen is not null) area = (screen.Bounds.Width, screen.Bounds.Height);
        }
        else
        {
            // The game sizes its window in logical pixels, 1280 x 720 unless set.
            var width = SettingInt("window_width");
            var height = SettingInt("window_height");
            area = ((int)Math.Round((width > 0 ? width : 1280) * scaling),
                    (int)Math.Round((height > 0 ? height : 720) * scaling));
        }
        if (area is not var (w, h) || w <= 0 || h <= 0) return null;
        if (!SettingBool("letterbox", true)) return (w, h);
        // Letterboxed to the game's 16:9.
        return (long)w * 9 > (long)h * 16 ? (h * 16 / 9, h) : (w, w * 9 / 16);
    }

    // LS-1.7: the GPU, its memory and Vulkan version and the CPU, with the
    // in-game preset that suits them. A software renderer (llvmpipe), a
    // missing Vulkan driver or one below 1.3 comes with a warning.
    private async Task ShowHardwareCheckAsync()
    {
        HardwareWarningText.IsVisible = DriverPageButton.IsVisible = false;
        var hardware = await HardwareAsync();
        if (hardware is not { } json)
        {
            HardwareText.Text = "The hardware check failed. Logs has the details.";
            RecommendationText.Text = "";
            UseRecommendedButton.IsEnabled = false;
            return;
        }
        HardwareText.Text = json.TryGetProperty("description", out var description) ? description.GetString() : "";
        if (json.TryGetProperty("recommendation", out var recommendation) &&
            recommendation.TryGetProperty("warning", out var warning) && warning.ValueKind == JsonValueKind.String)
        {
            HardwareWarningText.Text = warning.GetString();
            HardwareWarningText.IsVisible = true;
            DriverPageButton.IsVisible = json.TryGetProperty("driver_page", out var page) && page.ValueKind == JsonValueKind.String;
            // macOS has no driver download: the page is the troubleshooting guide.
            DriverPageButton.Content = Installation.IsMac ? "Open the troubleshooting guide" : "Open the driver download page";
        }
        UpdateRecommendationText();
    }

    private (string Preset, string Label, string Reason)? Recommendation()
    {
        if (_hardware is not { } json || !json.TryGetProperty("recommendation", out var recommendation)) return null;
        return (recommendation.GetProperty("preset").GetString() ?? "", recommendation.GetProperty("label").GetString() ?? "",
            recommendation.TryGetProperty("reason", out var reason) ? reason.GetString() ?? "" : "");
    }

    private void UpdateRecommendationText()
    {
        if (Recommendation() is not var (preset, label, reason)) return;
        var inUse = string.Equals(Setting("game_preset"), preset, StringComparison.Ordinal);
        RecommendationText.Text = $"Recommended: {label}. {reason}" + (inUse ? " In use." : "");
        UseRecommendedButton.Content = $"Use {label}";
        UseRecommendedButton.IsEnabled = !inUse && !_busy;
    }

    private void DriverPage_Click(object? sender, RoutedEventArgs e)
    {
        if (_hardware is { } json && json.TryGetProperty("driver_page", out var page) &&
            page.GetString() is { } url && url.StartsWith("https://", StringComparison.Ordinal))
            Installation.Open(url);
    }

    private async void UseRecommended_Click(object? sender, RoutedEventArgs e)
    {
        if (Recommendation() is not var (preset, label, _)) return;
        await ChangeGraphicsAsync("apply", $"{label} saved. Applies at the next start.",
            PanelChoices().Concat(["--game-preset", preset]));
    }

    private async void SaveGraphics_Click(object? sender, RoutedEventArgs e)
    {
        if (!await ChangeGraphicsAsync("apply", "Saved. Applies at the next start.", PanelChoices())) return;
        ShowPanel(Panel.None);
        UpdateSummary();
        StatusText.Text = "Settings saved. They apply at the next start.";
    }

    private void CloseGraphics_Click(object? sender, RoutedEventArgs e) => ShowPanel(Panel.None);

    private async void ResetGraphics_Click(object? sender, RoutedEventArgs e)
    {
        if (await Dialog.AskAsync(this, "Reset runtime settings",
                "Reset only the Pinyon Shift runtime settings? Your current pinyon_shift.toml will be backed up first.",
                "Reset", "Cancel") != "Reset")
            return;
        await ChangeGraphicsAsync("reset", "Reset to defaults. Applies at the next start.", revealBackup: true);
    }

    private async void RestoreGraphics_Click(object? sender, RoutedEventArgs e) =>
        await ChangeGraphicsAsync("restore", "Backup restored. Applies at the next start.");

    private async Task<bool> ChangeGraphicsAsync(string action, string success, IEnumerable<string>? options = null,
        bool revealBackup = false)
    {
        GraphicsControls.IsEnabled = false;
        UseRecommendedButton.IsEnabled = false;
        GraphicsStatusText.Text = action == "apply" ? "Saving…" : "Updating…";
        try
        {
            var result = await RunConfigAsync(action, options);
            if (!result.Succeeded)
            {
                GraphicsStatusText.Text = $"No settings were changed: {result.Error("The settings tool")}";
                return false;
            }
            ApplyGraphicsResult(result.Json!.Value);
            GraphicsStatusText.Text = success;
            UpdateSummary();
            // PowerShell prints "" when there is no backup and Python null.
            if (revealBackup && result.String("backup_path") is { Length: > 0 } backup && File.Exists(backup))
                Installation.Reveal(backup);
            return true;
        }
        finally
        {
            GraphicsControls.IsEnabled = true;
            UpdateRecommendationText();
        }
    }
}
