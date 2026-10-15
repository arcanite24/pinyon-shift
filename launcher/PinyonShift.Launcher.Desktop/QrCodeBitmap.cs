using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Media.Imaging;
using Avalonia.Platform;
using PinyonShift.Launcher.Sharing;

namespace PinyonShift.Launcher.Desktop;

// The shared QR code (launcher/Shared/QrCode.cs) as an Avalonia bitmap, for
// the Android panel's download link. Show it in an Image with
// RenderOptions.BitmapInterpolationMode="None" so the modules stay sharp.
public static class QrCodeBitmap
{
    public static WriteableBitmap ToBitmap(this QrCode code)
    {
        var image = code.ToGray8();
        var bitmap = new WriteableBitmap(new PixelSize(image.Side, image.Side), new Vector(96, 96),
            PixelFormat.Bgra8888, AlphaFormat.Opaque);
        using var buffer = bitmap.Lock();
        var row = new byte[image.Side * 4];
        for (var y = 0; y < image.Side; y++)
        {
            for (var x = 0; x < image.Side; x++)
            {
                var value = image.Pixels[y * image.Side + x];
                row[x * 4] = row[x * 4 + 1] = row[x * 4 + 2] = value;
                row[x * 4 + 3] = 255;
            }
            Marshal.Copy(row, 0, buffer.Address + y * buffer.RowBytes, row.Length);
        }
        return bitmap;
    }
}
