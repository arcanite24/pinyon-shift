using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;

namespace PinyonShift.Launcher.Desktop;

/// <summary>The Windows launcher's MessageBox questions: a small modal
/// window with a title, the text and one button per answer. Returns the
/// answer chosen, or null when the window was closed. The first answer has
/// the focus, so Enter (or A on a controller in Steam Input's desktop
/// layout) takes it; Escape closes.</summary>
public static class Dialog
{
    public static async Task<string?> AskAsync(Window owner, string title, string message, params string[] answers)
    {
        string? chosen = null;
        var window = new Window
        {
            Title = title,
            Width = 520,
            SizeToContent = SizeToContent.Height,
            CanResize = false,
            ShowInTaskbar = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Background = (IBrush?)owner.FindResource("SurfaceBrush"),
        };
        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal, Spacing = 10, HorizontalAlignment = HorizontalAlignment.Right,
        };
        Button? first = null;
        foreach (var answer in answers)
        {
            var button = new Button { Content = answer, MinWidth = 96, HorizontalContentAlignment = HorizontalAlignment.Center };
            button.Classes.Add("quiet");
            button.Click += (_, _) => { chosen = answer; window.Close(); };
            buttons.Children.Add(button);
            first ??= button;
        }
        window.Content = new StackPanel
        {
            Margin = new Thickness(26, 22),
            Spacing = 14,
            Children =
            {
                new TextBlock { Text = title, FontSize = 17, FontWeight = FontWeight.SemiBold, TextWrapping = TextWrapping.Wrap },
                new TextBlock
                {
                    Text = message, FontSize = 14, TextWrapping = TextWrapping.Wrap, LineHeight = 21,
                    Foreground = (IBrush?)owner.FindResource("MutedBrush"),
                },
                buttons,
            },
        };
        window.KeyDown += (_, e) => { if (e.Key == Key.Escape) window.Close(); };
        window.Opened += (_, _) => first?.Focus();
        await window.ShowDialog(owner);
        return chosen;
    }
}
