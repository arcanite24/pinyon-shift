using System.Text;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace PinyonShift.Launcher;

// A QR code (ISO/IEC 18004) for the Android panel's download link: byte
// mode, error correction level M, versions 1 to 10 (up to 213 bytes, far
// more than a LAN address and token). Follows the structure of Project
// Nayuki's reference generator; no package is needed for one short URL.
public sealed class QrCode
{
    // Level M, by version (index 0 unused).
    private static readonly int[] EccCodewordsPerBlock = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
    private static readonly int[] EccBlocks = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5];
    private const int MaxVersion = 10;
    private const int FormatBitsLevelM = 0;

    private readonly bool[,] _modules;
    private readonly bool[,] _function;

    public int Version { get; }
    public int Size { get; }

    public bool this[int x, int y] => _modules[y, x];

    private QrCode(int version)
    {
        Version = version;
        Size = version * 4 + 17;
        _modules = new bool[Size, Size];
        _function = new bool[Size, Size];
    }

    public static QrCode Encode(string text)
    {
        var data = Encoding.UTF8.GetBytes(text);
        var version = 1;
        for (; ; version++)
        {
            if (version > MaxVersion)
                throw new ArgumentException("The text is too long for a version 10 QR code.", nameof(text));
            var countBits = version <= 9 ? 8 : 16;
            if (4 + countBits + data.Length * 8 <= DataCodewords(version) * 8) break;
        }

        var bits = new List<bool>();
        void Append(int value, int length)
        {
            for (var i = length - 1; i >= 0; i--) bits.Add(((value >> i) & 1) != 0);
        }
        Append(0b0100, 4);  // byte mode
        Append(data.Length, version <= 9 ? 8 : 16);
        foreach (var b in data) Append(b, 8);
        var capacity = DataCodewords(version) * 8;
        Append(0, Math.Min(4, capacity - bits.Count));
        Append(0, (8 - bits.Count % 8) % 8);
        for (var pad = 0xEC; bits.Count < capacity; pad ^= 0xEC ^ 0x11) Append(pad, 8);

        var codewords = new byte[bits.Count / 8];
        for (var i = 0; i < bits.Count; i++)
            if (bits[i]) codewords[i >> 3] |= (byte)(1 << (7 - (i & 7)));

        var qr = new QrCode(version);
        qr.DrawFunctionPatterns();
        qr.DrawCodewords(AddEccAndInterleave(codewords, version));
        var bestMask = 0;
        var bestPenalty = int.MaxValue;
        for (var mask = 0; mask < 8; mask++)
        {
            qr.ApplyMask(mask);
            qr.DrawFormatBits(mask);
            var penalty = qr.Penalty();
            if (penalty < bestPenalty)
            {
                bestMask = mask;
                bestPenalty = penalty;
            }
            qr.ApplyMask(mask);  // XOR undoes it
        }
        qr.ApplyMask(bestMask);
        qr.DrawFormatBits(bestMask);
        return qr;
    }

    // One pixel per module with a four-module quiet zone; shown scaled with
    // nearest-neighbour sampling.
    public BitmapSource ToBitmap()
    {
        const int border = 4;
        var side = Size + border * 2;
        var pixels = new byte[side * side];
        Array.Fill(pixels, (byte)255);
        for (var y = 0; y < Size; y++)
            for (var x = 0; x < Size; x++)
                if (_modules[y, x]) pixels[(y + border) * side + x + border] = 0;
        var bitmap = BitmapSource.Create(side, side, 96, 96, PixelFormats.Gray8, null, pixels, side);
        bitmap.Freeze();
        return bitmap;
    }

    private static int RawDataModules(int version)
    {
        var result = (16 * version + 128) * version + 64;
        if (version >= 2)
        {
            var alignments = version / 7 + 2;
            result -= (25 * alignments - 10) * alignments - 55;
            if (version >= 7) result -= 36;
        }
        return result;
    }

    private static int DataCodewords(int version) =>
        RawDataModules(version) / 8 - EccCodewordsPerBlock[version] * EccBlocks[version];

    private static byte[] AddEccAndInterleave(byte[] data, int version)
    {
        var blocks = EccBlocks[version];
        var eccLength = EccCodewordsPerBlock[version];
        var raw = RawDataModules(version) / 8;
        var shortBlocks = blocks - raw % blocks;
        var shortLength = raw / blocks;
        var divisor = ReedSolomonDivisor(eccLength);
        var all = new List<byte[]>();
        for (int i = 0, k = 0; i < blocks; i++)
        {
            var length = shortLength - eccLength + (i < shortBlocks ? 0 : 1);
            var block = new byte[shortLength + 1];
            var dat = data.AsSpan(k, length).ToArray();
            k += length;
            var ecc = ReedSolomonRemainder(dat, divisor);
            // Short blocks keep a gap where the long ones have one more byte.
            dat.CopyTo(block, 0);
            ecc.CopyTo(block, i < shortBlocks ? length + 1 : length);
            all.Add(block);
        }
        var result = new List<byte>(raw);
        for (var i = 0; i < all[0].Length; i++)
            for (var j = 0; j < all.Count; j++)
                if (i != shortLength - eccLength || j >= shortBlocks)
                    result.Add(all[j][i]);
        return [.. result];
    }

    private static byte[] ReedSolomonDivisor(int degree)
    {
        var result = new byte[degree];
        result[degree - 1] = 1;
        var root = 1;
        for (var i = 0; i < degree; i++)
        {
            for (var j = 0; j < degree; j++)
            {
                result[j] = Multiply(result[j], root);
                if (j + 1 < degree) result[j] ^= result[j + 1];
            }
            root = Multiply(root, 0x02);
        }
        return result;
    }

    private static byte[] ReedSolomonRemainder(byte[] data, byte[] divisor)
    {
        var result = new byte[divisor.Length];
        foreach (var b in data)
        {
            var factor = b ^ result[0];
            Array.Copy(result, 1, result, 0, result.Length - 1);
            result[^1] = 0;
            for (var i = 0; i < result.Length; i++) result[i] ^= Multiply(divisor[i], factor);
        }
        return result;
    }

    private static byte Multiply(int x, int y)
    {
        var z = 0;
        for (var i = 7; i >= 0; i--)
        {
            z = (z << 1) ^ ((z >> 7) * 0x11D);
            z ^= ((y >> i) & 1) * x;
        }
        return (byte)z;
    }

    private void SetFunction(int x, int y, bool dark)
    {
        _modules[y, x] = dark;
        _function[y, x] = true;
    }

    private void DrawFunctionPatterns()
    {
        for (var i = 0; i < Size; i++)
        {
            SetFunction(6, i, i % 2 == 0);
            SetFunction(i, 6, i % 2 == 0);
        }
        DrawFinder(3, 3);
        DrawFinder(Size - 4, 3);
        DrawFinder(3, Size - 4);
        var positions = AlignmentPositions();
        for (var i = 0; i < positions.Length; i++)
            for (var j = 0; j < positions.Length; j++)
            {
                var last = positions.Length - 1;
                if ((i == 0 && j == 0) || (i == 0 && j == last) || (i == last && j == 0)) continue;
                for (var dy = -2; dy <= 2; dy++)
                    for (var dx = -2; dx <= 2; dx++)
                        SetFunction(positions[i] + dx, positions[j] + dy, Math.Max(Math.Abs(dx), Math.Abs(dy)) != 1);
            }
        DrawFormatBits(0);  // reserves the area; drawn again with the mask
        if (Version >= 7)
        {
            var remainder = Version;
            for (var i = 0; i < 12; i++) remainder = (remainder << 1) ^ ((remainder >> 11) * 0x1F25);
            var bits = Version << 12 | remainder;
            for (var i = 0; i < 18; i++)
            {
                var dark = ((bits >> i) & 1) != 0;
                int a = Size - 11 + i % 3, b = i / 3;
                SetFunction(a, b, dark);
                SetFunction(b, a, dark);
            }
        }
    }

    private void DrawFinder(int x, int y)
    {
        for (var dy = -4; dy <= 4; dy++)
            for (var dx = -4; dx <= 4; dx++)
            {
                var distance = Math.Max(Math.Abs(dx), Math.Abs(dy));
                int xx = x + dx, yy = y + dy;
                if (xx >= 0 && xx < Size && yy >= 0 && yy < Size)
                    SetFunction(xx, yy, distance != 2 && distance != 4);
            }
    }

    private int[] AlignmentPositions()
    {
        if (Version == 1) return [];
        var count = Version / 7 + 2;
        var step = (Version * 8 + count * 3 + 5) / (count * 4 - 4) * 2;
        var result = new int[count];
        result[0] = 6;
        for (int i = count - 1, position = Size - 7; i >= 1; i--, position -= step) result[i] = position;
        return result;
    }

    private void DrawFormatBits(int mask)
    {
        var data = FormatBitsLevelM << 3 | mask;
        var remainder = data;
        for (var i = 0; i < 10; i++) remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537);
        var bits = (data << 10 | remainder) ^ 0x5412;
        bool Bit(int i) => ((bits >> i) & 1) != 0;
        for (var i = 0; i <= 5; i++) SetFunction(8, i, Bit(i));
        SetFunction(8, 7, Bit(6));
        SetFunction(8, 8, Bit(7));
        SetFunction(7, 8, Bit(8));
        for (var i = 9; i < 15; i++) SetFunction(14 - i, 8, Bit(i));
        for (var i = 0; i < 8; i++) SetFunction(Size - 1 - i, 8, Bit(i));
        for (var i = 8; i < 15; i++) SetFunction(8, Size - 15 + i, Bit(i));
        SetFunction(8, Size - 8, true);
    }

    private void DrawCodewords(byte[] data)
    {
        var i = 0;
        for (var right = Size - 1; right >= 1; right -= 2)
        {
            if (right == 6) right = 5;
            for (var vertical = 0; vertical < Size; vertical++)
                for (var j = 0; j < 2; j++)
                {
                    var x = right - j;
                    var upward = ((right + 1) & 2) == 0;
                    var y = upward ? Size - 1 - vertical : vertical;
                    if (_function[y, x] || i >= data.Length * 8) continue;
                    _modules[y, x] = ((data[i >> 3] >> (7 - (i & 7))) & 1) != 0;
                    i++;
                }
        }
    }

    private void ApplyMask(int mask)
    {
        for (var y = 0; y < Size; y++)
            for (var x = 0; x < Size; x++)
            {
                var invert = mask switch
                {
                    0 => (x + y) % 2 == 0,
                    1 => y % 2 == 0,
                    2 => x % 3 == 0,
                    3 => (x + y) % 3 == 0,
                    4 => (x / 3 + y / 2) % 2 == 0,
                    5 => x * y % 2 + x * y % 3 == 0,
                    6 => (x * y % 2 + x * y % 3) % 2 == 0,
                    _ => ((x + y) % 2 + x * y % 3) % 2 == 0
                };
                if (invert && !_function[y, x]) _modules[y, x] = !_modules[y, x];
            }
    }

    private int Penalty()
    {
        var result = 0;
        for (var pass = 0; pass < 2; pass++)
        {
            for (var a = 0; a < Size; a++)
            {
                var runColor = false;
                var run = 0;
                var history = new int[7];
                for (var b = 0; b < Size; b++)
                {
                    var dark = pass == 0 ? _modules[a, b] : _modules[b, a];
                    if (dark == runColor)
                    {
                        run++;
                        if (run == 5) result += 3;
                        else if (run > 5) result++;
                    }
                    else
                    {
                        AddHistory(run, history);
                        if (!runColor) result += FinderLikePatterns(history) * 40;
                        runColor = dark;
                        run = 1;
                    }
                }
                if (runColor)
                {
                    AddHistory(run, history);
                    run = 0;
                }
                AddHistory(run + Size, history);
                result += FinderLikePatterns(history) * 40;
            }
        }
        for (var y = 0; y < Size - 1; y++)
            for (var x = 0; x < Size - 1; x++)
            {
                var color = _modules[y, x];
                if (color == _modules[y, x + 1] && color == _modules[y + 1, x] && color == _modules[y + 1, x + 1])
                    result += 3;
            }
        var darkCount = 0;
        foreach (var module in _modules) if (module) darkCount++;
        var total = Size * Size;
        var k = (Math.Abs(darkCount * 20 - total * 10) + total - 1) / total - 1;
        return result + k * 10;
    }

    private void AddHistory(int length, int[] history)
    {
        if (history[0] == 0) length += Size;  // the light border before the first run
        Array.Copy(history, 0, history, 1, history.Length - 1);
        history[0] = length;
    }

    private static int FinderLikePatterns(int[] h)
    {
        var n = h[1];
        var core = n > 0 && h[2] == n && h[3] == n * 3 && h[4] == n && h[5] == n;
        return (core && h[0] >= n * 4 && h[6] >= n ? 1 : 0) + (core && h[6] >= n * 4 && h[0] >= n ? 1 : 0);
    }
}
