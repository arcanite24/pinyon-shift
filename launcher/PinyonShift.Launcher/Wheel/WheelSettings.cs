using System.IO;
using System.Text.Json;

namespace PinyonShift.Launcher.Wheel;

/// <summary>The wheel screen's own preferences: which of its cards are open. Kept where Pinyon
/// Shift Configure kept them (%APPDATA%\PinyonShiftConfigure\settings.json), so they carry over.</summary>
public sealed class WheelSettings
{
    /// <summary>Left-column cards the player opened (all start collapsed).</summary>
    public Dictionary<string, bool> ExpandedCards { get; set; } = new();

    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };

    private static string FilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "PinyonShiftConfigure", "settings.json");
    // Where the app kept them while it was Pinyon Wheel Setup.
    private static string OldFilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "PinyonWheelSetup", "settings.json");

    public static WheelSettings Load()
    {
        try
        {
            string path = File.Exists(FilePath) ? FilePath : OldFilePath;
            if (File.Exists(path))
            {
                using var document = JsonDocument.Parse(File.ReadAllText(path));
                var settings = new WheelSettings();
                if (document.RootElement.TryGetProperty("ExpandedCards", out var cards) &&
                    cards.ValueKind == JsonValueKind.Object)
                {
                    foreach (var card in cards.EnumerateObject())
                        if (card.Value.ValueKind is JsonValueKind.True or JsonValueKind.False)
                            settings.ExpandedCards[card.Name] = card.Value.GetBoolean();
                }
                return settings;
            }
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException) { }
        return new WheelSettings();
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
