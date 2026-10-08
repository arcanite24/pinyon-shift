using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace PinyonShift.Launcher;

// A file the share offers, under a destination path relative to the app's
// files folder on the device ("game/base/...", "state/...").
public sealed record ShareFile(string Source, string Destination, long Length);

public sealed record ShareGroup(string Id, string Label, bool Selected, IReadOnlyList<ShareFile> Files)
{
    public long Bytes => Files.Sum(file => file.Length);
}

// Serves the Android package and the game files to the player's device on
// the local network while the launcher's Android panel shares
// (ONE_CLICK_SETUP_BACKLOG A-3, A-4). Only private-network addresses are
// answered. The download page and the package need the random token in the
// QR code's link; everything else needs the six-digit pairing code the
// panel shows, which changes each time sharing starts, and ten wrong codes
// stop the share. Only the files listed in the groups are served, by index.
// Nothing is received from the device.
public sealed class AndroidShare : IDisposable
{
    public const int PreferredPort = 47615;
    public const int DiscoveryPort = 47616;
    private const int MaxWrongCodes = 10;
    private const string DiscoverRequest = "PINYON-SHIFT-DISCOVER 1";

    private readonly string _apk;
    private readonly IReadOnlyList<ShareGroup> _groups;
    private readonly List<ShareFile> _files;
    private readonly JsonElement? _extras;
    private readonly CancellationTokenSource _stop = new();
    private TcpListener? _listener;
    private UdpClient? _discovery;
    private int _wrongCodes;

    public string Code { get; } = RandomNumberGenerator.GetInt32(0, 1_000_000).ToString("D6");
    public string Token { get; } = Convert.ToHexString(RandomNumberGenerator.GetBytes(12)).ToLowerInvariant();
    public int Port { get; private set; }
    public bool Locked => _wrongCodes >= MaxWrongCodes;

    // Status lines for the panel (raised on a worker thread).
    public event Action<string>? Activity;

    public AndroidShare(string apk, IReadOnlyList<ShareGroup> groups, object? extras = null)
    {
        _apk = apk;
        _groups = groups;
        _files = groups.SelectMany(group => group.Files).ToList();
        if (extras is not null) _extras = JsonSerializer.SerializeToElement(extras);
    }

    // All interfaces by default; a test binds the loopback address, which
    // also leaves discovery off.
    public void Start(IPAddress? bind = null)
    {
        bind ??= IPAddress.Any;
        try
        {
            _listener = new TcpListener(bind, PreferredPort);
            _listener.Start();
        }
        catch (SocketException)
        {
            _listener = new TcpListener(bind, 0);
            _listener.Start();
        }
        Port = ((IPEndPoint)_listener.LocalEndpoint).Port;
        _ = AcceptLoopAsync(_listener, _stop.Token);
        if (IPAddress.IsLoopback(bind)) return;
        try
        {
            _discovery = new UdpClient(new IPEndPoint(IPAddress.Any, DiscoveryPort)) { EnableBroadcast = true };
            _ = DiscoveryLoopAsync(_discovery, _stop.Token);
        }
        catch (SocketException)
        {
            // Another launcher answers; the device can still be given the address.
            Activity?.Invoke("Automatic discovery is unavailable; enter the address on the device.");
        }
    }

    // The PC's private IPv4 addresses on connected adapters, Wi-Fi and
    // Ethernet first.
    public static IReadOnlyList<IPAddress> LocalAddresses() =>
        NetworkInterface.GetAllNetworkInterfaces()
            .Where(adapter => adapter.OperationalStatus == OperationalStatus.Up &&
                              adapter.NetworkInterfaceType is not (NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel))
            .OrderBy(adapter => adapter.GetIPProperties().GatewayAddresses.Count == 0)
            .SelectMany(adapter => adapter.GetIPProperties().UnicastAddresses)
            .Select(address => address.Address)
            .Where(address => address.AddressFamily == AddressFamily.InterNetwork && IsPrivate(address) &&
                              !IPAddress.IsLoopback(address))
            .Distinct()
            .ToList();

    public static bool IsPrivate(IPAddress address)
    {
        if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
        if (IPAddress.IsLoopback(address)) return true;
        if (address.AddressFamily == AddressFamily.InterNetworkV6)
            return address.IsIPv6LinkLocal || address.IsIPv6UniqueLocal;
        var b = address.GetAddressBytes();
        return b[0] == 10 || (b[0] == 172 && b[1] >= 16 && b[1] <= 31) || (b[0] == 192 && b[1] == 168) ||
               (b[0] == 169 && b[1] == 254);
    }

    public string PageUrl(IPAddress address) => $"http://{address}:{Port}/{Token}";

    public void Dispose()
    {
        _stop.Cancel();
        try { _listener?.Stop(); } catch (SocketException) { }
        _discovery?.Dispose();
        _stop.Dispose();
    }

    private async Task DiscoveryLoopAsync(UdpClient udp, CancellationToken cancel)
    {
        var reply = Encoding.ASCII.GetBytes($"PINYON-SHIFT-HERE 1 {Port} {Environment.MachineName}");
        while (!cancel.IsCancellationRequested)
        {
            try
            {
                var request = await udp.ReceiveAsync(cancel);
                if (!IsPrivate(request.RemoteEndPoint.Address)) continue;
                if (Encoding.ASCII.GetString(request.Buffer).Trim() != DiscoverRequest) continue;
                await udp.SendAsync(reply, request.RemoteEndPoint, cancel);
            }
            catch (OperationCanceledException) { return; }
            catch (ObjectDisposedException) { return; }
            catch (SocketException) { }
        }
    }

    private async Task AcceptLoopAsync(TcpListener listener, CancellationToken cancel)
    {
        while (!cancel.IsCancellationRequested)
        {
            TcpClient client;
            try { client = await listener.AcceptTcpClientAsync(cancel); }
            catch (OperationCanceledException) { return; }
            catch (ObjectDisposedException) { return; }
            catch (SocketException) { return; }
            _ = Task.Run(() => ServeAsync(client, cancel), cancel);
        }
    }

    private async Task ServeAsync(TcpClient client, CancellationToken cancel)
    {
        using var _ = client;
        try
        {
            client.NoDelay = true;
            var remote = ((IPEndPoint)client.Client.RemoteEndPoint!).Address;
            await using var stream = client.GetStream();
            if (!IsPrivate(remote))
            {
                await RespondAsync(stream, 403, "text/plain", "Only devices on the local network are served.", cancel);
                return;
            }
            var request = await ReadRequestAsync(stream, cancel);
            if (request is null) return;
            await RouteAsync(stream, request, remote, cancel);
        }
        catch (Exception ex) when (ex is IOException or SocketException or OperationCanceledException or ObjectDisposedException)
        {
            // The device went away or sharing stopped; it resumes from where it was.
        }
    }

    private sealed record Request(string Method, string Path, Dictionary<string, string> Headers);

    private static async Task<Request?> ReadRequestAsync(NetworkStream stream, CancellationToken cancel)
    {
        var buffer = new byte[8192];
        var length = 0;
        while (true)
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancel);
            timeout.CancelAfter(TimeSpan.FromSeconds(15));
            var read = await stream.ReadAsync(buffer.AsMemory(length), timeout.Token);
            if (read == 0) return null;
            length += read;
            var end = buffer.AsSpan(0, length).IndexOf("\r\n\r\n"u8);
            if (end >= 0)
            {
                var lines = Encoding.ASCII.GetString(buffer, 0, end).Split("\r\n");
                var parts = lines[0].Split(' ');
                if (parts.Length < 2) return null;
                var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (var line in lines.Skip(1))
                {
                    var colon = line.IndexOf(':');
                    if (colon > 0) headers[line[..colon].Trim()] = line[(colon + 1)..].Trim();
                }
                var path = parts[1];
                var query = path.IndexOf('?');
                if (query >= 0) path = path[..query];
                return new Request(parts[0], path, headers);
            }
            if (length == buffer.Length) return null;
        }
    }

    private async Task RouteAsync(NetworkStream stream, Request request, IPAddress remote, CancellationToken cancel)
    {
        if (request.Method is not ("GET" or "HEAD"))
        {
            await RespondAsync(stream, 405, "text/plain", "Only downloads are served.", cancel);
            return;
        }
        var head = request.Method == "HEAD";
        var path = request.Path.TrimEnd('/');
        if (path == "/" + Token)
        {
            Activity?.Invoke($"{remote} opened the download page.");
            await RespondAsync(stream, 200, "text/html; charset=utf-8", DownloadPage(), cancel, head);
            return;
        }
        if (path == $"/{Token}/pinyon-shift.apk")
        {
            if (!head) Activity?.Invoke($"{remote} is downloading the Android package.");
            await SendFileAsync(stream, _apk, request, "application/vnd.android.package-archive", cancel, head,
                "attachment; filename=\"pinyon-shift.apk\"");
            return;
        }
        if (path == "/pinyon/v1/hello")
        {
            await RespondAsync(stream, 200, "application/json", JsonSerializer.Serialize(new
            {
                name = Environment.MachineName,
                version = typeof(AndroidShare).Assembly.GetName().Version?.ToString(3)
            }), cancel, head);
            return;
        }
        if (!path.StartsWith("/pinyon/v1/", StringComparison.Ordinal))
        {
            await RespondAsync(stream, 404, "text/plain", "Not found.", cancel, head);
            return;
        }
        if (Locked)
        {
            await RespondAsync(stream, 403, "text/plain", "Too many wrong codes. Start sharing again on the PC.", cancel, head);
            return;
        }
        var code = request.Headers.GetValueOrDefault("X-Pinyon-Code");
        if (code is null || !CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(code), Encoding.ASCII.GetBytes(Code)))
        {
            if (Interlocked.Increment(ref _wrongCodes) == MaxWrongCodes)
                Activity?.Invoke("Too many wrong pairing codes: sharing is locked. Stop and start it again for a new code.");
            else
                Activity?.Invoke($"{remote} sent a wrong pairing code.");
            await RespondAsync(stream, 403, "text/plain", "Wrong pairing code.", cancel, head);
            return;
        }
        if (path == "/pinyon/v1/manifest")
        {
            Activity?.Invoke($"{remote} connected with the pairing code.");
            var index = 0;
            await RespondAsync(stream, 200, "application/json", JsonSerializer.Serialize(new
            {
                schema_version = 1,
                name = Environment.MachineName,
                extras = _extras,
                groups = _groups.Select(group => new
                {
                    id = group.Id,
                    label = group.Label,
                    selected = group.Selected,
                    bytes = group.Bytes,
                    files = group.Files.Select(file => new { index = index++, path = file.Destination, size = file.Length })
                })
            }), cancel, head);
            return;
        }
        if (path.StartsWith("/pinyon/v1/file/", StringComparison.Ordinal) &&
            int.TryParse(path["/pinyon/v1/file/".Length..], out var fileIndex) && fileIndex >= 0 && fileIndex < _files.Count)
        {
            await SendFileAsync(stream, _files[fileIndex].Source, request, "application/octet-stream", cancel, head);
            return;
        }
        await RespondAsync(stream, 404, "text/plain", "Not found.", cancel, head);
    }

    private string DownloadPage() => $$"""
        <!doctype html>
        <html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Pinyon Shift for Android</title>
        <style>
          body { font-family: system-ui, sans-serif; background: #0f1a14; color: #e8efe9; margin: 0; padding: 28px 20px; line-height: 1.5; }
          main { max-width: 34rem; margin: 0 auto; }
          a.button { display: block; text-align: center; background: #f1ae36; color: #10180f; font-weight: 700;
                     padding: 16px; border-radius: 12px; text-decoration: none; font-size: 1.15rem; margin: 22px 0; }
          ol { padding-left: 1.2rem; } li { margin: 8px 0; } .muted { color: #9fb2a5; font-size: .9rem; }
          code { background: #1d2b22; padding: 2px 6px; border-radius: 6px; }
        </style></head>
        <body><main>
          <h1>Pinyon Shift for Android</h1>
          <p>Built on {{WebUtility.HtmlEncode(Environment.MachineName)}} from your own disc.</p>
          <a class="button" href="/{{Token}}/pinyon-shift.apk" download>Download the app</a>
          <ol>
            <li>Open the downloaded <code>pinyon-shift.apk</code>. If Android asks, allow this browser to install apps.</li>
            <li>Open Pinyon Shift. It finds this PC and asks for the six-digit code shown in the launcher.</li>
            <li>Keep the launcher's Android panel open while the game files copy over.</li>
          </ol>
          <p class="muted">Served only on your local network while sharing is on. Nothing is uploaded.</p>
        </main></body></html>
        """;

    private static async Task RespondAsync(NetworkStream stream, int status, string type, string body,
        CancellationToken cancel, bool head = false)
    {
        var bytes = Encoding.UTF8.GetBytes(body);
        var header = $"HTTP/1.1 {status} {Reason(status)}\r\nContent-Type: {type}\r\nContent-Length: {bytes.Length}\r\n" +
                     "Cache-Control: no-store\r\nConnection: close\r\n\r\n";
        await stream.WriteAsync(Encoding.ASCII.GetBytes(header), cancel);
        if (!head) await stream.WriteAsync(bytes, cancel);
    }

    // The whole file, or the rest of it from a "Range: bytes=N-" offset, so
    // an interrupted copy resumes.
    private static async Task SendFileAsync(NetworkStream stream, string path, Request request, string type,
        CancellationToken cancel, bool head, string? disposition = null)
    {
        FileStream file;
        try { file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16, useAsync: true); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            await RespondAsync(stream, 404, "text/plain", "The file is no longer on the PC.", cancel, head);
            return;
        }
        await using var _ = file;
        var length = file.Length;
        long start = 0;
        var status = 200;
        if (request.Headers.TryGetValue("Range", out var range) && range.StartsWith("bytes=", StringComparison.Ordinal))
        {
            var spec = range["bytes=".Length..];
            var dash = spec.IndexOf('-');
            if (dash > 0 && long.TryParse(spec[..dash], out var from) && from >= 0)
            {
                if (from >= length && length > 0)
                {
                    var unsatisfied = $"HTTP/1.1 416 Range Not Satisfiable\r\nContent-Range: bytes */{length}\r\n" +
                                      "Content-Length: 0\r\nConnection: close\r\n\r\n";
                    await stream.WriteAsync(Encoding.ASCII.GetBytes(unsatisfied), cancel);
                    return;
                }
                start = from;
                status = 206;
            }
        }
        var header = new StringBuilder()
            .Append($"HTTP/1.1 {status} {Reason(status)}\r\nContent-Type: {type}\r\n")
            .Append($"Content-Length: {length - start}\r\nAccept-Ranges: bytes\r\nCache-Control: no-store\r\n");
        if (status == 206) header.Append($"Content-Range: bytes {start}-{length - 1}/{length}\r\n");
        if (disposition is not null) header.Append($"Content-Disposition: {disposition}\r\n");
        header.Append("Connection: close\r\n\r\n");
        await stream.WriteAsync(Encoding.ASCII.GetBytes(header.ToString()), cancel);
        if (head) return;
        file.Seek(start, SeekOrigin.Begin);
        await file.CopyToAsync(stream, 1 << 18, cancel);
    }

    private static string Reason(int status) => status switch
    {
        200 => "OK",
        206 => "Partial Content",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        _ => "Error"
    };
}
