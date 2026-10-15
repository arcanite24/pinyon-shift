using System.Windows.Media;
using System.Windows.Media.Imaging;
using PinyonShift.Launcher.Sharing;

namespace PinyonShift.Launcher;

// The shared QR code (launcher/Shared/QrCode.cs) as a WPF bitmap.
public static class QrCodeBitmap
{
    // One pixel per module with a four-module quiet zone; shown scaled with
    // nearest-neighbour sampling.
    public static BitmapSource ToBitmap(this QrCode code)
    {
        var image = code.ToGray8();
        var bitmap = BitmapSource.Create(image.Side, image.Side, 96, 96, PixelFormats.Gray8, null, image.Pixels,
            image.Side);
        bitmap.Freeze();
        return bitmap;
    }
}
