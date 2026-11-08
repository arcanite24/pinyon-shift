using System.Text.Json;
using System.Text.Json.Serialization;

namespace PinyonShift.Launcher.Mods;

// The mod manager's data (FEATURE_BACKLOG FB-9.1), shared by both launchers: what
// `pinyon.py mods ... --json` (tools/pinyon_mods.py) prints, and the words each
// launcher shows for it. The launchers only draw it; the tool does the work.
public sealed class ModsStatus
{
    public List<ModEntry> Mods { get; set; } = [];
    public ModSave Save { get; set; } = new();
    public List<string> Missing { get; set; } = [];
    public string Build { get; set; } = "";
    [JsonPropertyName("mods_root")] public string ModsRoot { get; set; } = "";
    public List<string> Installed { get; set; } = [];
    [JsonPropertyName("also_enabled")] public List<string> AlsoEnabled { get; set; } = [];
    public string? Error { get; set; }

    private static readonly JsonSerializerOptions Options = new() { PropertyNameCaseInsensitive = true };

    // The last line of the tool's output is its JSON object.
    public static ModsStatus? Parse(string stdout)
    {
        var text = stdout.Trim();
        var json = text[(text.LastIndexOf('\n') + 1)..];
        if (!json.StartsWith('{')) return null;
        return JsonSerializer.Deserialize<ModsStatus>(json, Options);
    }

    // Shows a switch before the tool has made it (it takes a second or two), so the
    // mod's dot and line change at the click; the tool's answer replaces the list.
    // The launchers leave load order alone: mods load in the order they were switched on
    // (`mods enable` appends), which matters only when two change the same thing, and
    // `pinyon.py mods move` still reorders them.
    public void Preview(ModEntry mod, bool enabled) => mod.Enabled = enabled;

    // The note above the mods, shown only when it has something to say: what the last
    // change did to the save the next start plays (SaveChangeText, kept until another
    // change replaces it or the view is opened again), and mods switched on but not
    // installed. Empty means the launchers hide the note.
    public string Notice(string saveChange)
    {
        var parts = new List<string>();
        if (saveChange.Length > 0) parts.Add(saveChange);
        if (Missing.Count > 0) parts.Add($"Switched on but not installed: {string.Join(", ", Missing)}.");
        return string.Join(" ", parts);
    }

    // What a change just made does to the save the next start plays (docs/MODDING.md, "Your
    // saves stay separate"); empty when it plays the same save. The two moments that matter
    // are the first mod that changes the save (the game moves to a copy) and the last one
    // switched off or removed (the game goes back to the player's own save, without the
    // progress made with mods). At most two lines at 940 x 640, with the missing-mods note.
    public string SaveChangeText(ModSave? before)
    {
        if (before is null || (before.Kind == Save.Kind && before.Profile == Save.Profile)) return "";
        return Save.Kind switch
        {
            "modded" => Save.ModdedCopy
                ? "Your mods change your save again, so from the next start they play the modded copy of it, where you left it. Your own save stays as it is."
                : "A mod you switched on changes your save, so from the next start your mods play a separate copy of it. Your own save stays as it is; switch those mods off to play it again.",
            "own-mod-save" => $"{Title(Save.Mod)} starts its own new save from the next start. Your own save stays as it is.",
            _ => before.Kind == "own-mod-save"
                ? $"The next start plays your own save again. {Title(before.Mod)}'s save stays as you left it."
                : "No mod you have on changes your save now, so the next start plays your own save. Your modded progress stays in its copy for when you switch such a mod on again."
        };
    }

    private string Title(string? name) => Mods.FirstOrDefault(m => m.Name == name)?.Title ?? name ?? "";
}

public sealed class ModSave
{
    public string Kind { get; set; } = "own";
    public string Profile { get; set; } = "user";
    public string? Mod { get; set; }
    // The shared modded copy (user-modded) exists.
    [JsonPropertyName("modded_copy")] public bool ModdedCopy { get; set; }
}

// One option a mod offers: the launcher shows a list of its choices, and picking one runs
// `pinyon.py mods option`, which applies at the next start.
public sealed class ModOption
{
    public string Key { get; set; } = "";
    public string Title { get; set; } = "";
    public string Description { get; set; } = "";
    public List<ModChoice> Choices { get; set; } = [];
    public string Value { get; set; } = "";

    public bool HasDescription => Description.Length > 0;
    public string ValueLabel => Choices.FirstOrDefault(c => c.Value == Value)?.Label ?? Value;
}

public sealed class ModChoice
{
    public string Value { get; set; } = "";
    public string Label { get; set; } = "";

    // Lists draw their selected item as text; the launcher's list style ignores DisplayMemberPath.
    public override string ToString() => Label;
}

public sealed class ModEntry
{
    public string Name { get; set; } = "";
    public string Title { get; set; } = "";
    public string Version { get; set; } = "";
    public string Author { get; set; } = "";
    public string Description { get; set; } = "";
    public string Url { get; set; } = "";
    public List<string> Images { get; set; } = [];
    public bool Enabled { get; set; }
    public bool Builtin { get; set; }
    [JsonPropertyName("managed_by")] public string? ManagedBy { get; set; }
    [JsonPropertyName("shares_save")] public bool SharesSave { get; set; }
    public string Profile { get; set; } = "";
    public List<string> Contents { get; set; } = [];
    public List<string> Builds { get; set; } = [];
    public List<string> Requires { get; set; } = [];
    public List<string> Conflicts { get; set; } = [];
    // The choices the mod declares in mod.toml (tools/mod_options.py); empty for most mods.
    public List<ModOption> Options { get; set; } = [];
    public List<string> Problems { get; set; } = [];

    public bool HasProblems => Problems.Count > 0;
    public bool HasUrl => Url.Length > 0;
    public bool HasOptions => Options.Count > 0;
    public bool CanRemove => !Builtin && ManagedBy is null;
    // on, off or problem: the dot beside the name.
    public string State => Enabled ? (HasProblems ? "problem" : "on") : "off";

    public string StateText => Enabled
        ? (HasProblems ? $"On · won't load: {Problems[0]}" : "On")
        : HasProblems ? $"Off · {Problems[0]}" : "Off";

    public string Byline
    {
        get
        {
            var parts = new List<string>();
            if (Version.Length > 0) parts.Add($"Version {Version}");
            if (Author.Length > 0) parts.Add($"by {Author}");
            if (Builtin) parts.Add("built in");
            parts.Add(Name);
            return string.Join(" · ", parts);
        }
    }

    public string DescriptionText => Description.Length > 0 ? Description : "This mod has no description.";

    public string ProblemText => HasProblems
        ? (Enabled ? "The game won't load it: " : "The game wouldn't load it: ") + string.Join("; ", Problems) + "."
        : "";

    public string Facts
    {
        get
        {
            var lines = new List<string>();
            if (Contents.Count > 0) lines.Add($"Changes: {string.Join(", ", Contents)}");
            lines.Add(Builds.Count == 0 ? "For: every build" : $"For: the {string.Join(" and ", Builds)}");
            lines.Add(Profile.Length > 0 ? "Save: starts its own new save"
                : SharesSave && !Contents.Contains("database") ? "Save: keeps your own save"
                : "Save: plays a separate copy of your save");
            if (Requires.Count > 0) lines.Add($"Needs: {string.Join(", ", Requires)}");
            if (Conflicts.Count > 0) lines.Add($"Can't run with: {string.Join(", ", Conflicts)}");
            if (ManagedBy is not null) lines.Add($"Made on the {ManagedBy} screen");
            return string.Join("\n", lines);
        }
    }

    public string ToggleText => Enabled ? "Switch off" : "Switch on";
    public string ToggleAccessibleName => $"{ToggleText} {Title}";
    public string AccessibleName => $"{Title}, {StateText}";
}
