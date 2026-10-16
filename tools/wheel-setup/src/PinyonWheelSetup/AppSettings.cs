using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using PinyonWheelSetup.Theming;

namespace PinyonWheelSetup;

/// <summary>The setup's own preferences (%APPDATA%\PinyonWheelSetup\settings.json).</summary>
public sealed class AppSettings
{
    public ThemeChoice Theme { get; set; } = ThemeChoice.Dark;
    /// <summary>The config the player browsed to, if it is not where the launcher puts it.</summary>
    public string? ConfigPath { get; set; }
    /// <summary>Left-column cards the player opened (all start collapsed).</summary>
    public Dictionary<string, bool> ExpandedCards { get; set; } = new();

    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() },
    };

    private static string FilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "PinyonWheelSetup", "settings.json");

    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(FilePath))
                return JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(FilePath), Options) ?? new AppSettings();
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException) { }
        return new AppSettings();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            File.WriteAllText(FilePath, JsonSerializer.Serialize(this, Options));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }
}
