using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;
using PinyonShift.Launcher.Wheel.Bindings;
using PinyonShift.Launcher.Wheel.Diagnostics;
using PinyonShift.Launcher.Wheel.Input;
using InputType = PinyonShift.Launcher.Wheel.Bindings.InputType;

namespace PinyonShift.Launcher.Wheel;

// The launcher's wheel screen (it was the standalone Pinyon Shift Configure app).
// The launcher opens it with its game config and closes it with Done; SDL runs only while it is open.

public partial class WheelSetupView : UserControl
{
    private readonly WheelSettings settings = WheelSettings.Load();
    private bool open;

    /// <summary>Done, or the end of a self-test: the launcher hides the screen.</summary>
    public event EventHandler? DoneRequested;
    private readonly DeviceManager devices = new();
    private readonly BindingSet set = new();
    private readonly TelemetrySettings telemetry = new();
    private readonly DispatcherTimer timer = new(DispatcherPriority.Input) { Interval = TimeSpan.FromMilliseconds(15) };
    private readonly Storyboard pulse;

    private string? configPath;
    private Dictionary<string, string> configValues = new();
    private bool dirty;
    private bool loadingUi;
    private bool selfTest;

    // Binding step state
    private Capture? capture;
    private bool addingInput;  // the step adds an input to a button instead of replacing its binding
    private bool guided;
    private int stepIndex;

    // Status line
    private string? info;
    private string? error;
    private bool gameRunning;
    private DateTime nextGameCheck;

    private sealed record FfbChoice(string Text, DeviceKey? Key, string? Unresolved)
    {
        public override string ToString() => Text;
    }

    public WheelSetupView()
    {
        InitializeComponent();
        pulse = (Storyboard)FindResource("PulseStoryboard");

        BindingList.ItemsSource = set.Items;
        ChipList.ItemsSource = set.Buttons.ToList();
        DeviceList.ItemsSource = devices.Devices;
        devices.DevicesChanged += OnDevicesChanged;
        timer.Tick += (_, _) => Tick();
    }

    /// <summary>Opens the screen on <paramref name="gameConfig"/> (the launcher's
    /// pinyon_shift.toml), logging to <paramref name="logDirectory"/>. With
    /// <paramref name="selfTestDirectory"/> it drives every step with virtual devices, saves
    /// screenshots there and then asks to close.</summary>
    public async Task OpenAsync(string? gameConfig, string? logDirectory, string? selfTestDirectory = null)
    {
        if (open) return;
        open = true;
        Log.Start(logDirectory);
        Log.Watching(true);
        HideBanner();
        info = null;
        error = null;
        if (!devices.Start())
        {
            ShowBanner(devices.InitError + $" The launcher cannot read controllers. Details: {Log.FilePath}");
        }
        selfTest = selfTestDirectory != null;
        configPath = gameConfig;
        Log.Write($"config in use: {configPath ?? "(none)"}");
        LoadConfig();
        foreach (var key in Cards.Keys) SetCardExpanded(key, settings.ExpandedCards.GetValueOrDefault(key), save: false);
        timer.Start();
        Focus();
        if (selfTestDirectory != null) await RunSelfTestAsync(selfTestDirectory);
    }

    /// <summary>Stops reading devices (SDL is closed) and keeps the card layout.</summary>
    public void Shutdown()
    {
        if (!open) return;
        open = false;
        if (capture != null) EndCapture(finished: false);
        timer.Stop();
        devices.Dispose();
        Log.Watching(false);
        if (!selfTest) settings.Save();
    }

    private void Done_Click(object sender, RoutedEventArgs e)
    {
        if (dirty && set.Steering.Input != null && !gameRunning) SaveToGame(null);
        DoneRequested?.Invoke(this, EventArgs.Empty);
    }

    // -----------------------------------------------------------------------------------------
    // Config

    private void LoadConfig()
    {
        error = null;
        if (configPath == null || !File.Exists(configPath))
        {
            ConfigPathText.Text = "Not found";
            ConfigWarning.Text = "No pinyon_shift.toml yet. Run the game once from the launcher, close it, then come back. Or Browse to it.";
            ConfigWarning.Visibility = Visibility.Visible;
            configValues = new();
        }
        else
        {
            ConfigPathText.Text = configPath;
            ConfigWarning.Visibility = Visibility.Collapsed;
            try
            {
                configValues = GameConfig.Read(configPath);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                configValues = new();
                error = "Could not read the config: " + ex.Message;
            }
        }
        foreach (var (key, value) in configValues.Where(kv => kv.Key.StartsWith("wheel_")))
            Log.Write($"config {key} = {value}");
        set.Load(configValues, devices.Devices);
        telemetry.Load(configValues);
        TelemetryFromModel();
        dirty = false;
        UiFromSet();
        UpdateCardSummaries();
        RefreshFfbChoices();
        UpdateStatus();
    }

    private void OnDevicesChanged()
    {
        DeviceCount.Text = devices.Devices.Count == 1 ? "1 device" : $"{devices.Devices.Count} devices";
        NoDevicesText.Visibility = devices.Devices.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        // Devices can arrive after the config was read; resolve its bindings again while nothing was changed.
        if (!dirty && capture == null) set.Load(configValues, devices.Devices);
        RefreshFfbChoices();
    }

    private void Browse_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Find pinyon_shift.toml",
            Filter = "Pinyon Shift config (pinyon_shift.toml)|pinyon_shift.toml|TOML files (*.toml)|*.toml",
            InitialDirectory = configPath != null ? Path.GetDirectoryName(configPath) :
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PinyonShift"),
        };
        if (dialog.ShowDialog(Window.GetWindow(this)) != true) return;
        configPath = dialog.FileName;
        LoadConfig();
    }

    private void Save_Click(object sender, RoutedEventArgs e) => SaveToGame(null);

    private bool backedUp;

    /// <summary>Writes the bindings into the game config. The first save of a session keeps a backup.
    /// <paramref name="bound"/> names what a single Bind just set, for the status line.</summary>
    private bool SaveToGame(string? bound)
    {
        info = null;
        error = null;
        bool saved = false;
        if (configPath == null || !File.Exists(configPath))
        {
            error = "There is no game config to save to. Run the game once from the launcher, close it, then Save again.";
        }
        else if (set.Steering.Input == null)
        {
            if (bound != null) info = $"Bound {bound}. Bind the steering too, then it saves.";
            else error = "Bind the steering first: Start guided setup, or Bind on the Steering row.";
        }
        else if (gameRunning && !selfTest)
        {
            if (bound != null) info = $"Bound {bound}, not saved yet: close Pinyon Shift, then Save to game.";
            else error = "Close Pinyon Shift first. It reads the config when it starts, and saves its own settings over it on exit.";
        }
        else
        {
            try
            {
                var lines = set.ConfigLines(devices.Devices);
                foreach (var (k, v) in lines) Log.Write($"save {k} = {v}");
                string? backup = GameConfig.Update(configPath, lines, backup: !backedUp);
                if (backup != null) backedUp = true;
                Log.Write($"saved {configPath}" + (backup != null ? $", backup {backup}" : ""));
                TryWriteRecord(lines);
                configValues = GameConfig.Read(configPath);
                dirty = false;
                saved = true;
                info = bound != null
                    ? $"Bound and saved {bound}."
                    : "Saved to the game config" + (backup != null ? $". The old one is kept as {Path.GetFileName(backup)}." : ".") +
                      " Start the game from the launcher.";
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                error = "Could not save: " + ex.Message;
                Log.Error("save", ex);
            }
        }
        UpdateStatus();
        return saved;
    }

    /// <summary>A copy of the saved lines beside the EXE, in case the config is replaced later.</summary>
    private static void TryWriteRecord(List<(string Key, string Value)> lines)
    {
        try
        {
            string dir = Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
            File.WriteAllLines(Path.Combine(dir, "last-wheel-bindings.toml"),
                new[] { $"# Pinyon Shift wheel screen {DateTime.Now:yyyy-MM-dd HH:mm}" }.Concat(lines.Select(l => $"{l.Key} = {l.Value}")));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
    }

    // -----------------------------------------------------------------------------------------
    // Live loop

    private void Tick()
    {
        Log.Beat();
        try
        {
            TickCore();
        }
        catch (Exception e)
        {
            if (tickErrors.Add(e.GetType().FullName + e.Message)) Log.Error("tick", e);
        }
        Log.Beat();
    }

    private readonly HashSet<string> tickErrors = [];
    private string lastDetection = "";

    private void TickCore()
    {
        devices.Poll();
        set.UpdateLive(devices.Devices);
        if (capture != null)
        {
            capture.Update();
            if (capture.Candidate != null && devices.Find(capture.CandidateDevice) is { } dev)
            {
                // Show the pending binding everywhere, as it would be saved.
                set.Evaluate(capture.Item, capture.Candidate, dev, out double v, out bool p, out string t);
                capture.Item.Value = v;
                capture.Item.Pressed = p;
                capture.Item.ValueText = t;
            }
            UpdateStepPanel();
            AutoCommitSingleBind();
        }
        UpdateLiveView();

        var now = DateTime.UtcNow;
        if (now >= nextGameCheck)
        {
            nextGameCheck = now.AddSeconds(2);
            bool running = !selfTest && GameConfig.GameRunning();
            if (running != gameRunning)
            {
                gameRunning = running;
                if (running) ShowBanner("Pinyon Shift is running. Close it before you Save: it rewrites its config on exit.");
                else HideBanner();
                UpdateStatus();
            }
        }
    }

    private void UpdateLiveView()
    {
        var steer = set.Steering;
        bool steerLive = steer.IsBound || capture?.Item == steer && capture.Detected;
        WheelRotation.Angle = steer.Value * 450;  // drawn for a 900° wheel
        SteerText.Text = steerLive ? $"{WheelMath.Signed((int)Math.Round(steer.Value * 100))} %" : "—";
        SetPedal(set.Get("CLUTCH"), ClutchBar, ClutchText);
        SetPedal(set.Get("BRAKE"), BrakeBar, BrakeText);
        SetPedal(set.Get("THROTTLE"), ThrottleBar, ThrottleText);
    }

    private void SetPedal(BindingItem item, Controls.ValueBar bar, TextBlock text)
    {
        bool live = item.IsBound || capture?.Item == item && capture.Detected;
        bar.Value = item.Value;
        bar.Opacity = live ? 1 : 0.45;
        text.Text = live ? $"{Math.Round(item.Value * 100)} %" : "—";
    }

    // -----------------------------------------------------------------------------------------
    // Binding steps

    private void Guided_Click(object sender, RoutedEventArgs e)
    {
        if (capture != null)
        {
            EndCapture(finished: false);
            return;
        }
        info = null;
        error = null;
        guided = true;
        stepIndex = 0;
        BeginStep(set.Items[0]);
    }

    private void BeginStep(BindingItem item)
    {
        Log.Write($"step: {item.Key}{(guided ? $" ({stepIndex + 1} of {set.Items.Count})" : " (single)")}");
        foreach (var i in set.Items) i.IsCurrent = false;
        item.IsCurrent = true;
        capture = new Capture(set, devices, item);
        StepPanel.Visibility = Visibility.Visible;
        GuidedIcon.Text = "";
        GuidedLabel.Text = guided ? "Stop setup" : "Cancel";
        StepTitle.Text = item.Label;
        StepCounter.Text = guided ? $"Step {stepIndex + 1} of {set.Items.Count}" : "Binding one control";
        StepPrompt.Text = guided ? item.Prompt
            : item.Prompt + (item.Kind == BindKind.Button
                ? " It binds and saves as soon as you press it."
                : " It binds and saves when you let go.");
        BackButton.Visibility = guided ? Visibility.Visible : Visibility.Collapsed;
        BackButton.IsEnabled = guided && stepIndex > 0;
        SkipButton.Content = guided ? "Skip" : "Cancel";
        SkipButton.ToolTip = guided ? "Keep this control as it is and go on" : "Keep the binding as it was";
        NextLabel.Text = !guided || stepIndex == set.Items.Count - 1 ? "Finish" : "Next";
        NextButton.Visibility = guided ? Visibility.Visible : Visibility.Collapsed;
        StepBar.Centered = item.Kind == BindKind.Steering;
        pulse.Begin(ListenDot, true);
        if (BindingList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement row) row.BringIntoView();
        UpdateStepPanel();
        UpdateStatus();
    }

    private void UpdateStepPanel()
    {
        if (capture == null) return;
        var item = capture.Item;
        var candidate = capture.Candidate;
        NextButton.IsEnabled = candidate != null;
        if (candidate == null)
        {
            DetectText.Text = item.Kind switch
            {
                BindKind.Steering => "Listening — turn the wheel left…",
                BindKind.Pedal => "Listening — press the pedal…",
                _ => "Listening — press a button…",
            };
            StepLive.Visibility = Visibility.Collapsed;
            StepWarning.Visibility = Visibility.Collapsed;
            return;
        }
        pulse.Stop(ListenDot);
        ListenDot.Opacity = 1;
        var dev = devices.Find(capture.CandidateDevice);
        string detection = $"{item.Key}: \"{dev?.Name}\" {candidate.Describe()} rest {capture.Rest} inverted {candidate.Inverted}";
        if (detection != lastDetection)
        {
            Log.Write("detected " + detection);
            lastDetection = detection;
        }
        string where = $"{dev?.Name ?? candidate.Device?.Name} · {candidate.Describe()}";
        if (candidate.Type == InputType.Axis) where += $" · rests at {WheelMath.Signed(capture.Rest)}";
        DetectText.Text = "Detected: " + where;
        StepLive.Visibility = Visibility.Visible;
        StepBar.Value = item.Value;
        short raw = dev != null && candidate.Type == InputType.Axis && candidate.Index < dev.Axes.Length ? dev.Axes[candidate.Index] : (short)0;
        StepValue.Text = candidate.Type == InputType.Axis
            ? $"{item.ValueText}   raw {WheelMath.Signed(raw)}"
            : item.Pressed ? "pressed" : "released";
        StepInvert.Visibility = candidate.Type == InputType.Axis ? Visibility.Visible : Visibility.Collapsed;
        StepInvert.IsChecked = candidate.Inverted;

        string? warning = null;
        if (capture.RestsMidRange)
            warning = "This axis rests in the middle of its range, so the game would read it as half pressed. Calibrate it to its full range in the device's own software, or Rebind.";
        else if (item.Kind == BindKind.Button &&
                 set.Buttons.FirstOrDefault(b => b != item && b.AllInputs.Any(i => i.SameInput(candidate))) is { } other)
            warning = $"This is also bound to {other.Label}. Next moves it here.";
        StepWarning.Text = warning ?? "";
        StepWarning.Visibility = warning != null ? Visibility.Visible : Visibility.Collapsed;
    }

    private void StepNext_Click(object sender, RoutedEventArgs e) => CommitAndAdvance();

    private DateTime singleReleasedAt;

    /// <summary>A single Bind needs no Finish: a button binds and saves as soon as it is pressed; an
    /// axis once it has moved through its travel and come back (its direction needs the travel).</summary>
    private void AutoCommitSingleBind()
    {
        if (guided || capture?.Candidate is not { } candidate) return;
        bool immediate = candidate.Type != InputType.Axis;
        if (!immediate)
        {
            if (!capture.CandidateReleased() || capture.RestsMidRange)
            {
                singleReleasedAt = default;
                return;
            }
            if (singleReleasedAt == default) singleReleasedAt = DateTime.UtcNow;
            if (DateTime.UtcNow - singleReleasedAt < TimeSpan.FromMilliseconds(300)) return;
        }
        singleReleasedAt = default;
        var item = capture.Item;
        CommitAndAdvance();
        SaveToGame($"{item.Label} \u2192 {item.BindingText}");
    }

    private void CommitAndAdvance()
    {
        if (capture?.Candidate is not { } candidate) return;
        var item = capture.Item;
        if (item.Kind == BindKind.Button)
        {
            foreach (var other in set.Buttons.Where(b => b != item).ToList())
                other.RemoveInput(candidate);
        }
        if (addingInput && item.Kind == BindKind.Button) item.AddInput(candidate);
        else item.Input = candidate;
        addingInput = false;
        Log.Write($"bound {item.Key} -> {item.BindingText} (inverted {candidate.Inverted})");
        dirty = true;
        if (item.Kind == BindKind.Steering) RefreshFfbChoices();
        Advance();
    }

    private void StepSkip_Click(object sender, RoutedEventArgs e)
    {
        // No H-shifter: skipping 1st gear while it is unbound skips the other gears too.
        if (guided && capture?.Item is { Key: BindingSet.FirstGear, IsBound: false })
        {
            EndCapture(finished: true);
            return;
        }
        Advance();
    }

    private void StepUnbind_Click(object sender, RoutedEventArgs e)
    {
        if (capture == null) return;
        capture.Item.ClearInputs();
        dirty = true;
        Advance();
    }

    private void StepBack_Click(object sender, RoutedEventArgs e)
    {
        if (!guided || stepIndex == 0) return;
        stepIndex--;
        BeginStep(set.Items[stepIndex]);
    }

    private void StepRebind_Click(object sender, RoutedEventArgs e)
    {
        if (capture == null) return;
        capture.Reset();
        pulse.Begin(ListenDot, true);
        UpdateStepPanel();
    }

    private void StepInvert_Click(object sender, RoutedEventArgs e) => capture?.SetInvert(StepInvert.IsChecked == true);

    private void Advance()
    {
        if (guided && stepIndex < set.Items.Count - 1)
        {
            stepIndex++;
            BeginStep(set.Items[stepIndex]);
        }
        else
        {
            EndCapture(finished: true);
        }
    }

    private void EndCapture(bool finished)
    {
        addingInput = false;
        bool wasGuided = guided;
        capture = null;
        guided = false;
        pulse.Stop(ListenDot);
        foreach (var i in set.Items) i.IsCurrent = false;
        StepPanel.Visibility = Visibility.Collapsed;
        GuidedIcon.Text = "";
        GuidedLabel.Text = "Start guided setup";
        if (finished && wasGuided)
            info = "All set. Check the live view: turn the wheel, press the pedals and buttons. Then Save to game.";
        UpdateStatus();
    }

    private void RowBind_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.Tag is not BindingItem item) return;
        info = null;
        error = null;
        guided = false;
        addingInput = false;
        BeginStep(item);
    }

    /// <summary>+ on a button row: one more input for the same game button, kept with the others.</summary>
    private void RowAdd_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.Tag is not BindingItem item || item.Kind != BindKind.Button) return;
        info = null;
        error = null;
        guided = false;
        BeginStep(item);
        addingInput = true;
        info = $"Press another input for {item.Label}; it keeps {item.BindingText}.";
        UpdateStatus();
    }

    private void RowClear_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.Tag is not BindingItem item) return;
        item.ClearInputs();
        dirty = true;
        if (item.Kind == BindKind.Steering) RefreshFfbChoices();
        UpdateStatus();
    }

    private void RowInvert_Click(object sender, RoutedEventArgs e)
    {
        dirty = true;
        UpdateStatus();
    }

    private void View_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (capture == null || Keyboard.FocusedElement is ComboBox or ComboBoxItem or TextBox) return;
        if (e.Key == Key.Enter && capture.Detected)
        {
            CommitAndAdvance();
            e.Handled = true;
        }
        else if (e.Key == Key.Escape)
        {
            EndCapture(finished: false);
            e.Handled = true;
        }
    }

    // -----------------------------------------------------------------------------------------
    // Force feedback and tuning

    private void RefreshFfbChoices()
    {
        loadingUi = true;
        var steerKey = set.Steering.Input?.Device;
        var steerDev = BindingSet.Resolve(steerKey, devices.Devices);
        var choices = new List<FfbChoice>
        {
            new(steerDev != null ? $"Steering device ({steerDev.Name})" : "Steering device", null, null),
        };
        foreach (var d in devices.Devices.Where(d => d.Haptic && (steerKey == null || !steerKey.Is(d))))
            choices.Add(new(d.Name, DeviceKey.Of(d), null));
        if (set.FfbDevice != null && !choices.Any(c => c.Key == set.FfbDevice))
            choices.Add(new($"{set.FfbDevice.Name} (not connected)", set.FfbDevice, null));
        if (set.FfbDeviceUnresolved != null)
            choices.Add(new($"{set.FfbDeviceUnresolved} (not connected)", null, set.FfbDeviceUnresolved));
        FfbDeviceBox.ItemsSource = choices;
        FfbDeviceBox.SelectedItem =
            choices.FirstOrDefault(c => set.FfbDevice != null ? c.Key == set.FfbDevice :
                                        set.FfbDeviceUnresolved != null ? c.Unresolved == set.FfbDeviceUnresolved : c.Key == null && c.Unresolved == null)
            ?? choices[0];
        loadingUi = false;
    }

    private void FfbDeviceBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (loadingUi || FfbDeviceBox.SelectedItem is not FfbChoice choice) return;
        set.FfbDevice = choice.Key;
        set.FfbDeviceUnresolved = choice.Unresolved;
        dirty = true;
        UpdateStatus();
    }

    private async void TestFfb_Click(object sender, RoutedEventArgs e)
    {
        var key = (FfbDeviceBox.SelectedItem as FfbChoice)?.Key ?? set.Steering.Input?.Device;
        var dev = BindingSet.Resolve(key, devices.Devices);
        FfbTestText.Visibility = Visibility.Visible;
        FfbTestText.SetResourceReference(TextBlock.ForegroundProperty, "TextSecondaryBrush");
        if (dev == null)
        {
            FfbTestText.Text = key == null ? "Bind the steering first, or pick a device." : "That device is not connected.";
            FfbTestText.SetResourceReference(TextBlock.ForegroundProperty, "ErrorTextBrush");
            return;
        }
        TestButton.IsEnabled = false;
        FfbTestText.Text = $"Testing \"{dev.Name}\"…";
        try
        {
            FfbTestText.Text = await devices.TestForceAsync(dev, FfbInvertBox.IsChecked == true);
        }
        finally
        {
            TestButton.IsEnabled = true;
        }
    }

    private void UiFromSet()
    {
        loadingUi = true;
        FfbModeBox.SelectedIndex = Math.Max(0, Array.IndexOf(BindingSet.FfbModes, set.FfbMode));
        StrengthSlider.Value = set.FfbStrength;
        MinForceSlider.Value = set.FfbMinForce;
        SpringSlider.Value = set.FfbSpring;
        DamperSlider.Value = set.FfbDamper;
        FrictionSlider.Value = set.FfbFriction;
        InertiaSlider.Value = set.FfbInertia;
        RumbleEngineSlider.Value = set.FfbRumbleEngine;
        RumbleRoadSlider.Value = set.FfbRumbleRoad;
        Wheel900Box.IsChecked = set.Wheel900;
        FfbInvertBox.IsChecked = set.FfbInvert;
        FfbTraceBox.IsChecked = set.FfbTrace;
        ScaleSlider.Value = set.SteeringScale;
        SteerDeadzoneSlider.Value = set.SteeringDeadzone;
        ThrottleBottomSlider.Value = set.PedalDeadzones["THROTTLE"].Bottom;
        ThrottleTopSlider.Value = set.PedalDeadzones["THROTTLE"].Top;
        BrakeBottomSlider.Value = set.PedalDeadzones["BRAKE"].Bottom;
        BrakeTopSlider.Value = set.PedalDeadzones["BRAKE"].Top;
        ClutchBottomSlider.Value = set.PedalDeadzones["CLUTCH"].Bottom;
        ClutchTopSlider.Value = set.PedalDeadzones["CLUTCH"].Top;
        loadingUi = false;
        UpdateTuningText();
    }

    private void Tuning_Changed(object sender, RoutedEventArgs e)
    {
        if (loadingUi || !IsLoaded) return;
        set.FfbMode = BindingSet.FfbModes[Math.Max(0, FfbModeBox.SelectedIndex)];
        set.FfbStrength = (int)StrengthSlider.Value;
        set.FfbMinForce = (int)MinForceSlider.Value;
        set.FfbSpring = (int)SpringSlider.Value;
        set.FfbDamper = (int)DamperSlider.Value;
        set.FfbFriction = (int)FrictionSlider.Value;
        set.FfbInertia = (int)InertiaSlider.Value;
        set.FfbRumbleEngine = (int)RumbleEngineSlider.Value;
        set.FfbRumbleRoad = (int)RumbleRoadSlider.Value;
        set.Wheel900 = Wheel900Box.IsChecked == true;
        set.FfbInvert = FfbInvertBox.IsChecked == true;
        set.FfbTrace = FfbTraceBox.IsChecked == true;
        set.SteeringScale = (int)ScaleSlider.Value;
        set.SteeringDeadzone = (int)SteerDeadzoneSlider.Value;
        set.PedalDeadzones["THROTTLE"] = ((int)ThrottleBottomSlider.Value, (int)ThrottleTopSlider.Value);
        set.PedalDeadzones["BRAKE"] = ((int)BrakeBottomSlider.Value, (int)BrakeTopSlider.Value);
        set.PedalDeadzones["CLUTCH"] = ((int)ClutchBottomSlider.Value, (int)ClutchTopSlider.Value);
        dirty = true;
        UpdateTuningText();
        UpdateStatus();
    }

    private void TelemetryFromModel()
    {
        loadingUi = true;
        TelemetryBox.IsChecked = telemetry.Enabled;
        TelemetryFormatBox.SelectedIndex = telemetry.Horizon ? 0 : 1;
        TelemetryTargetBox.Text = telemetry.Target;
        MovingOnlyBox.IsChecked = telemetry.MovingOnly;
        loadingUi = false;
    }

    private void Telemetry_Changed(object sender, RoutedEventArgs e)
    {
        if (loadingUi || !IsLoaded) return;
        string target = TelemetryTargetBox.Text.Trim();
        if (target.Length > 0 && !target.Contains(':')) target += TelemetrySettings.DefaultPort;
        telemetry.Enabled = TelemetryBox.IsChecked == true;
        telemetry.Horizon = TelemetryFormatBox.SelectedIndex != 1;
        telemetry.MovingOnly = MovingOnlyBox.IsChecked == true;
        telemetry.Target = target.Length > 0 ? target : TelemetrySettings.DefaultTarget;
        TelemetryTargetBox.Text = telemetry.Target;
        SaveSettings(telemetry.ConfigLines(), "Telemetry", telemetry.Summary());
        UpdateCardSummaries();
        UpdateStatus();
    }

    /// <summary>Writes one card's keys into the game config at once, apart from the bindings.</summary>
    private void SaveSettings(List<(string Key, string Value)> lines, string what, string summary)
    {
        info = null;
        error = null;
        if (configPath == null || !File.Exists(configPath))
        {
            error = "There is no game config to save to. Run the game once from the launcher, close it, then try again.";
            return;
        }
        if (gameRunning && !selfTest)
        {
            error = "Close Pinyon Shift first. It saves its own settings over the config when it exits.";
            return;
        }
        try
        {
            foreach (var (k, v) in lines) Log.Write($"save {k} = {v}");
            string? backup = GameConfig.Update(configPath, lines, backup: !backedUp);
            if (backup != null) backedUp = true;
            configValues = GameConfig.Read(configPath);
            info = $"{what} saved: {summary}. It applies from the next game start.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            error = "Could not save: " + ex.Message;
            Log.Error("save " + what, ex);
        }
    }

    // -----------------------------------------------------------------------------------------
    // Collapsible cards

    private Dictionary<string, (FrameworkElement Body, TextBlock Chevron)> Cards => new()
    {
        ["config"] = (ConfigBody, ConfigChevron),
        ["telemetry"] = (TelemetryBody, TelemetryChevron),
        ["devices"] = (DevicesBody, DevicesChevron),
        ["ffb"] = (FfbBody, FfbChevron),
        ["steering"] = (SteeringBody, SteeringChevron),
    };

    private void CardToggle_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.Tag is not string key || !Cards.TryGetValue(key, out var card)) return;
        SetCardExpanded(key, card.Body.Visibility != Visibility.Visible, save: true);
    }

    private void SetCardExpanded(string key, bool expanded, bool save)
    {
        if (!Cards.TryGetValue(key, out var card)) return;
        card.Body.Visibility = expanded ? Visibility.Visible : Visibility.Collapsed;
        card.Chevron.Text = expanded ? "\uE70E" : "\uE70D";  // chevron up / down
        if (!save || selfTest) return;
        settings.ExpandedCards[key] = expanded;
        settings.Save();
    }

    /// <summary>What each collapsed card's header shows.</summary>
    private void UpdateCardSummaries()
    {
        bool found = configPath != null && File.Exists(configPath);
        ConfigSummary.Text = found ? "Found" : "Not found";
        ConfigSummary.SetResourceReference(TextBlock.ForegroundProperty, found ? "TextSecondaryBrush" : "ErrorTextBrush");
        FfbSummary.Text = set.FfbMode switch
        {
            "off" => "Off",
            "rumble" => "Rumble only",
            _ => $"On · {set.FfbStrength} %" + (set.FfbInvert ? " · reversed" : ""),
        };
        SteeringSummary.Text = set.Wheel900 ? "900°" : "speed-sensitive";
        TelemetrySummary.Text = telemetry.Summary();
    }

    private void UpdateTuningText()
    {
        UpdateCardSummaries();
        StrengthValue.Text = $"{(int)StrengthSlider.Value} %";
        MinForceValue.Text = $"{(int)MinForceSlider.Value} %";
        SpringValue.Text = $"{(int)SpringSlider.Value} %";
        DamperValue.Text = $"{(int)DamperSlider.Value} %";
        FrictionValue.Text = $"{(int)FrictionSlider.Value} %";
        InertiaValue.Text = $"{(int)InertiaSlider.Value} %";
        RumbleEngineValue.Text = $"{(int)RumbleEngineSlider.Value} %";
        RumbleRoadValue.Text = $"{(int)RumbleRoadSlider.Value} %";
        ScaleValue.Text = $"{(int)ScaleSlider.Value} %";
        SteerDeadzoneValue.Text = $"{(int)SteerDeadzoneSlider.Value} %";
        foreach (var (slider, text) in new[] {
                     (ThrottleBottomSlider, ThrottleBottomValue), (ThrottleTopSlider, ThrottleTopValue),
                     (BrakeBottomSlider, BrakeBottomValue), (BrakeTopSlider, BrakeTopValue),
                     (ClutchBottomSlider, ClutchBottomValue), (ClutchTopSlider, ClutchTopValue) })
            text.Text = $"{(int)slider.Value} %";
    }

    // -----------------------------------------------------------------------------------------
    // Status, banner, theme

    private void UpdateStatus()
    {
        // A resource reference, so the colour follows a theme switch.
        if (error != null)
        {
            StatusText.Text = error;
            StatusText.SetResourceReference(TextBlock.ForegroundProperty, "ErrorTextBrush");
            return;
        }
        StatusText.SetResourceReference(TextBlock.ForegroundProperty, "TextBrush");
        if (capture != null)
            StatusText.Text = guided ? $"Guided setup: {capture.Item.Label}." : $"Binding {capture.Item.Label}.";
        else if (info != null)
            StatusText.Text = info;
        else if (set.Steering.Input == null)
            StatusText.Text = "Start the guided setup to bind your wheel, pedals and buttons.";
        else
            StatusText.Text = dirty ? "Unsaved changes. Press Save to game when you're done." : "Ready. Bindings match the game config.";
    }

    private void ShowBanner(string text)
    {
        BannerText.Text = text;
        Banner.Visibility = Visibility.Visible;
    }

    private void HideBanner() => Banner.Visibility = Visibility.Collapsed;


    // -----------------------------------------------------------------------------------------
    // Self-test: --selftest <toml> <screenshot dir>. Plugs in SDL virtual devices and drives every
    // step the way a player would, taking screenshots along the way, then saves.

    private async Task RunSelfTestAsync(string outDir)
    {
        Directory.CreateDirectory(outDir);
        var log = new List<string>();
        try
        {
            uint wheelId = Sdl.AttachVirtual("Wheel Base", 0x1234, 0xBEAD, Sdl.JoystickTypeWheel, 6, 16, 1);
            uint pedalsId = Sdl.AttachVirtual("SimJack Pro Pedals", 0x16D0, 0x0D5A, Sdl.JoystickTypeUnknown, 3, 4, 0);
            // A button box: buttons, no axes or hats (the case that once broke every device's reading).
            uint boxId = Sdl.AttachVirtual("Button Box", 0x1209, 0xB0B0, Sdl.JoystickTypeUnknown, 0, 12, 0);
            await Task.Delay(700);  // the next device scan opens them
            var wheel = devices.Find(wheelId)?.Handle ?? throw new InvalidOperationException("virtual wheel not opened");
            var pedals = devices.Find(pedalsId)?.Handle ?? throw new InvalidOperationException("virtual pedals not opened");
            var box = devices.Find(boxId)?.Handle ?? throw new InvalidOperationException("virtual button box not opened");
            void Axis(IntPtr d, int a, int v) => Sdl.SDL_SetJoystickVirtualAxis(d, a, (short)Math.Clamp(v, -32768, 32767));
            void Btn(IntPtr d, int b, bool down) => Sdl.SDL_SetJoystickVirtualButton(d, b, down);
            void Hat(IntPtr d, byte v) => Sdl.SDL_SetJoystickVirtualHat(d, 0, v);
            Axis(pedals, 0, -32768);
            Axis(pedals, 1, 32767);   // a brake wired backwards
            Axis(pedals, 2, -32768);
            Axis(wheel, 5, -32768);   // a handbrake lever at rest
            await Task.Delay(200);
            LoadConfig();
            await Task.Delay(300);
            Snap(outDir, "01-start");
            foreach (var key in Cards.Keys) SetCardExpanded(key, true, save: false);

            Guided_Click(this, new RoutedEventArgs());
            await Task.Delay(300);
            Snap(outDir, "02-steering-listening");
            Axis(wheel, 0, -30000);
            await Task.Delay(400);
            Snap(outDir, "03-steering-detected");
            Axis(wheel, 0, 0);
            await Task.Delay(200);
            Next();

            Axis(pedals, 0, 32767);
            await Task.Delay(400);
            Axis(pedals, 0, 10000);  // part way back, to show the live bar
            await Task.Delay(200);
            Snap(outDir, "04-throttle-detected");
            Axis(pedals, 0, -32768);
            await Task.Delay(150);
            Next();

            Axis(pedals, 1, -32768);
            await Task.Delay(400);
            Axis(pedals, 1, 32767);
            await Task.Delay(150);
            Next();

            StepUnbind_Click(this, new RoutedEventArgs());  // no clutch
            await Task.Delay(150);

            // Buttons in FH1 wheel-layout order: shift up (RB), shift down (LB), handbrake (B),
            // clutch button (A, left unbound), rewind (Y, on the button box), activate (X),
            // map (BACK, a lever), pause (START), horn (LS), look back (RS, pedal set), d-pad (hat)
            async Task Press(Action down, Action up, string? snap = null)
            {
                down();
                await Task.Delay(250);
                if (snap != null) Snap(outDir, snap);
                up();
                await Task.Delay(150);
                Next();
            }
            await Press(() => Btn(wheel, 5, true), () => Btn(wheel, 5, false), "05-button-detected");
            await Press(() => Btn(wheel, 4, true), () => Btn(wheel, 4, false));
            await Press(() => Btn(wheel, 1, true), () => Btn(wheel, 1, false));
            StepUnbind_Click(this, new RoutedEventArgs());
            await Task.Delay(150);
            await Press(() => Btn(box, 5, true), () => Btn(box, 5, false));
            await Press(() => Btn(wheel, 2, true), () => Btn(wheel, 2, false));
            await Press(() => Axis(wheel, 5, 32767), () => Axis(wheel, 5, -32768));
            await Press(() => Btn(wheel, 9, true), () => Btn(wheel, 9, false));
            await Press(() => Btn(wheel, 6, true), () => Btn(wheel, 6, false));
            await Press(() => Btn(pedals, 0, true), () => Btn(pedals, 0, false));
            foreach (byte dir in new byte[] { WheelMath.HatUp, WheelMath.HatDown, WheelMath.HatLeft, WheelMath.HatRight })
                await Press(() => Hat(wheel, dir), () => Hat(wheel, 0));
            StepSkip_Click(this, new RoutedEventArgs());  // no H-shifter: skips every gear
            await Task.Delay(150);
            log.Add("guided finished: " + (capture == null));

            // The live view with some input held.
            Axis(wheel, 0, -12000);
            Axis(pedals, 0, -32768 + (int)(0.7 * 65535));
            Axis(pedals, 1, 32767 - (int)(0.3 * 65535));
            Btn(wheel, 0, true);
            Hat(wheel, WheelMath.HatLeft);
            await Task.Delay(400);
            Snap(outDir, "06-live-view");

            Save_Click(this, new RoutedEventArgs());
            await Task.Delay(300);
            Snap(outDir, "08-saved");
            LeftScroll.ScrollToEnd();
            await Task.Delay(300);
            Snap(outDir, "09-pedal-deadzones");
            LeftScroll.ScrollToVerticalOffset(330);
            await Task.Delay(300);
            Snap(outDir, "10-force-feedback");

            // Single Bind: no Finish. A button binds and saves on press; an axis when let go.
            Btn(wheel, 0, false);
            Hat(wheel, 0);
            Axis(wheel, 0, 0);
            Axis(pedals, 0, -32768);
            Axis(pedals, 1, 32767);
            await Task.Delay(300);
            void BindRow(string key) =>
                RowBind_Click(new Button { Tag = set.Get(key) }, new RoutedEventArgs());
            BindRow("LB");
            await Task.Delay(250);
            Btn(wheel, 7, true);
            await Task.Delay(300);
            log.Add($"single bind LB: {set.Get("LB").BindingText}, capture open: {capture != null}, status: {StatusText.Text}");
            Snap(outDir, "11-single-bind-button");
            Btn(wheel, 7, false);
            await Task.Delay(200);
            // + adds a second input for the same game button; both press it, both are saved.
            RowAdd_Click(new Button { Tag = set.Get("LB") }, new RoutedEventArgs());
            await Task.Delay(250);
            Btn(box, 9, true);
            await Task.Delay(300);
            Btn(box, 9, false);
            await Task.Delay(200);
            Btn(box, 9, true);
            await Task.Delay(150);
            log.Add($"second input LB: {set.Get("LB").BindingText}; pressed by the box: {set.Get("LB").Pressed}");
            Btn(box, 9, false);
            await Task.Delay(150);
            var afterAdd = GameConfig.Read(configPath!);
            log.Add("saved wheel_buttons: " + (afterAdd.TryGetValue("wheel_buttons", out var wb) ? wb : "(missing)"));
            Snap(outDir, "11b-second-input");
            BindRow("THROTTLE");
            await Task.Delay(250);
            Axis(pedals, 2, 32767);
            await Task.Delay(300);
            log.Add($"single bind THROTTLE while held: capture open: {capture != null}");
            Axis(pedals, 2, -32768);
            await Task.Delay(600);
            log.Add($"single bind THROTTLE after release: {set.Get("THROTTLE").BindingText}, capture open: {capture != null}, status: {StatusText.Text}");
            log.Add("status: " + StatusText.Text);
            foreach (var item in set.Items) log.Add($"{item.Key}: {item.BindingText}");

            // Telemetry: saved at once.
            LeftScroll.ScrollToHome();
            TelemetryBox.IsChecked = true;
            Telemetry_Changed(TelemetryBox, new RoutedEventArgs());
            TelemetryFormatBox.SelectedIndex = 1;
            await Task.Delay(100);
            TelemetryFormatBox.SelectedIndex = 0;
            await Task.Delay(200);
            var saved = GameConfig.Read(configPath!);
            string Get(string k) => saved.TryGetValue(k, out var v) ? v : "(missing)";
            log.Add($"telemetry: {TelemetrySummary.Text}; udp {Get("telemetry_udp")}, format {Get("telemetry_udp_format")}, " +
                    $"moving only {Get("telemetry_udp_moving_only")}, target {Get("telemetry_udp_target")}");
            Snap(outDir, "12-telemetry");
        }
        catch (Exception ex)
        {
            log.Add("FAILED: " + ex);
        }
        File.WriteAllLines(Path.Combine(outDir, "selftest.log"), log);
        DoneRequested?.Invoke(this, EventArgs.Empty);

        void Next()
        {
            if (capture?.Detected == true) CommitAndAdvance();
            else log.Add($"not detected at {capture?.Item.Key}");
        }
    }

    private void Snap(string dir, string name)
    {
        UpdateLayout();
        FrameworkElement root = this;
        var dpi = VisualTreeHelper.GetDpi(this);
        var bitmap = new RenderTargetBitmap((int)(root.ActualWidth * dpi.DpiScaleX), (int)(root.ActualHeight * dpi.DpiScaleY),
                                            dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32);
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            dc.DrawRectangle((Brush)FindResource("WindowBrush"), null, new Rect(0, 0, root.ActualWidth, root.ActualHeight));
            dc.DrawRectangle(new VisualBrush(root), null, new Rect(0, 0, root.ActualWidth, root.ActualHeight));
        }
        bitmap.Render(visual);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var file = File.Create(Path.Combine(dir, name + ".png"));
        encoder.Save(file);
    }
}
