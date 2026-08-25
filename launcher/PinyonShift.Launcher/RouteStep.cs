using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Media;

namespace PinyonShift.Launcher;

public enum StepState { Waiting, Active, Complete, Failed }

public sealed class RouteStep : INotifyPropertyChanged
{
    public static readonly string[] StageOrder = ["verify", "tools", "extract", "build", "play"];

    private Brush _brush = new SolidColorBrush(Color.FromRgb(57, 64, 57));
    private string _marker;

    public RouteStep(string stage, string title, string detail, string marker)
    {
        Stage = stage;
        Title = title;
        Detail = detail;
        _marker = marker;
    }

    public string Stage { get; }
    public string Title { get; }
    public string Detail { get; }
    public Brush Brush { get => _brush; private set { _brush = value; Notify(); } }
    public string Marker { get => _marker; private set { _marker = value; Notify(); } }
    public StepState State { get; private set; }

    public event PropertyChangedEventHandler? PropertyChanged;

    public void SetState(StepState state, Brush waiting, Brush active, Brush complete, Brush failed)
    {
        State = state;
        Brush = state switch
        {
            StepState.Active => active,
            StepState.Complete => complete,
            StepState.Failed => failed,
            _ => waiting
        };
        Marker = state switch
        {
            StepState.Complete => "✓",
            StepState.Failed => "!",
            _ => (Array.IndexOf(StageOrder, Stage.ToLowerInvariant()) + 1).ToString()
        };
    }

    private void Notify([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
