using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace PinyonShift.Launcher.Wheel.Controls;

/// <summary>
/// A rounded meter: 0..1 filled from the start (pedals, buttons) or −1..1 filled out from the
/// centre (steering). Horizontal or vertical (vertical fills from the bottom).
/// </summary>
public sealed class ValueBar : FrameworkElement
{
    public static readonly DependencyProperty ValueProperty = DependencyProperty.Register(
        nameof(Value), typeof(double), typeof(ValueBar), new FrameworkPropertyMetadata(0.0, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty CenteredProperty = DependencyProperty.Register(
        nameof(Centered), typeof(bool), typeof(ValueBar), new FrameworkPropertyMetadata(false, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty OrientationProperty = DependencyProperty.Register(
        nameof(Orientation), typeof(Orientation), typeof(ValueBar), new FrameworkPropertyMetadata(Orientation.Horizontal, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty FillProperty = DependencyProperty.Register(
        nameof(Fill), typeof(Brush), typeof(ValueBar), new FrameworkPropertyMetadata(Brushes.DodgerBlue, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty TrackProperty = DependencyProperty.Register(
        nameof(Track), typeof(Brush), typeof(ValueBar), new FrameworkPropertyMetadata(Brushes.Gray, FrameworkPropertyMetadataOptions.AffectsRender));

    public double Value { get => (double)GetValue(ValueProperty); set => SetValue(ValueProperty, value); }
    public bool Centered { get => (bool)GetValue(CenteredProperty); set => SetValue(CenteredProperty, value); }
    public Orientation Orientation { get => (Orientation)GetValue(OrientationProperty); set => SetValue(OrientationProperty, value); }
    public Brush Fill { get => (Brush)GetValue(FillProperty); set => SetValue(FillProperty, value); }
    public Brush Track { get => (Brush)GetValue(TrackProperty); set => SetValue(TrackProperty, value); }

    protected override void OnRender(DrawingContext dc)
    {
        double w = ActualWidth, h = ActualHeight;
        if (w <= 0 || h <= 0) return;
        bool vertical = Orientation == Orientation.Vertical;
        double radius = (vertical ? w : h) / 2;
        dc.DrawRoundedRectangle(Track, null, new Rect(0, 0, w, h), radius, radius);

        double length = vertical ? h : w;
        double v = Centered ? Math.Clamp(Value, -1, 1) : Math.Clamp(Value, 0, 1);
        double start, end;
        if (Centered)
        {
            double mid = length / 2;
            start = Math.Min(mid, mid + v * mid);
            end = Math.Max(mid, mid + v * mid);
        }
        else
        {
            start = 0;
            end = v * length;
        }
        if (end - start < 0.5) return;
        Rect fill = vertical
            ? new Rect(0, h - end, w, end - start)  // from the bottom
            : new Rect(start, 0, end - start, h);
        dc.PushClip(new RectangleGeometry(new Rect(0, 0, w, h), radius, radius));
        dc.DrawRectangle(Fill, null, fill);
        dc.Pop();
        if (Centered)
        {
            // Centre tick
            var pen = new Pen(Track, 0);
            double mid = length / 2;
            var tick = vertical ? new Rect(0, mid - 0.75, w, 1.5) : new Rect(mid - 0.75, 0, 1.5, h);
            dc.DrawRectangle(Fill, pen, tick);
        }
    }
}
